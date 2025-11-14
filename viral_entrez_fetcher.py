import pandas as pd
from Bio import SeqIO, Entrez
import asyncio
import logging
from multiprocessing import Pool, cpu_count, Manager
from aiohttp import ClientSession, TCPConnector
from aiohttp_retry import RetryClient, ExponentialRetry
from tqdm import tqdm
from termcolor import colored
import time
from typing import Optional, Tuple, Dict, List
import xml.etree.ElementTree as ET

## Basic configurations for logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    handlers=[
                        logging.FileHandler('viral_fetcher.log', mode='w', encoding='utf-8'),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

## Global variables
miRNA_db = None
stored_cache = None
mirBase_df = None

## IMPORTANT: Set your email for NCBI Entrez (required by NCBI)
ENTREZ_EMAIL = "your.email@example.com"
ENTREZ_API_KEY = None  ## Optional but recommended for higher rate limits

## NCBI E-utilities base URLs
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def init_process(miRNA_path: str) -> None:
    """Initialize global variables for each process"""
    global miRNA_db, stored_cache, mirBase_df
    logger.info("Loading miRNA database...")
    miRNA_db = load_miRNA_db(miRNA_path)
    stored_cache = {
        "Genes": {},
        "Sequences": {}
    }

def load_miRNA_db(miRNA_path: str) -> dict:
    """Load miRNA database from FASTA file"""
    return {record.id: (str(record.seq), len(record.seq))
            for record in SeqIO.parse(miRNA_path, "fasta")}

async def fetchWithRetry(url: str, session: RetryClient, params: dict = None) -> Optional[str]:
    """
    Fetch data from NCBI with retry logic

    Args:
        url: NCBI API endpoint
        session: RetryClient session
        params: Query parameters

    Returns:
        Response text or None if failed
    """
    try:
        async with session.get(url=url, params=params) as response:
            if response.status == 200:
                return await response.text()
            else:
                logger.warning(f"Request failed with status {response.status} for URL: {url}")
                return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {str(e)}")
        return None

async def getGeneInfo(entrez_id: int, session: RetryClient) -> Optional[Dict]:
    """
    Fetch gene information from NCBI Gene database

    Args:
        entrez_id: NCBI Entrez Gene ID
        session: RetryClient session

    Returns:
        Dictionary with gene info or None
    """
    url = f"{NCBI_EUTILS_BASE}/esummary.fcgi"
    params = {
        "db": "gene",
        "id": entrez_id,
        "retmode": "xml"
    }

    if ENTREZ_API_KEY:
        params["api_key"] = ENTREZ_API_KEY

    logger.info(f"Fetching gene info for Entrez ID: {entrez_id}")

    data = await fetchWithRetry(url=url, session=session, params=params)

    if not data:
        logger.error(f"No gene info found for Entrez ID: {entrez_id}")
        return None

    try:
        root = ET.fromstring(data)
        gene_name = None
        description = None

        # Parse XML response
        for docsum in root.findall(".//DocumentSummary"):
            gene_name = docsum.findtext("Name")
            description = docsum.findtext("Description")

        logger.info(f"Gene info for {entrez_id}: {gene_name} - {description}")
        return {
            "gene_name": gene_name,
            "description": description,
            "entrez_id": entrez_id
        }
    except ET.ParseError as e:
        logger.error(f"Error parsing XML for Entrez ID {entrez_id}: {str(e)}")
        return None

async def getNucleotideIDs(entrez_id: int, session: RetryClient) -> List[str]:
    """
    Get nucleotide sequence IDs linked to a gene Entrez ID

    Args:
        entrez_id: NCBI Entrez Gene ID
        session: RetryClient session

    Returns:
        List of nucleotide accession IDs
    """
    url = f"{NCBI_EUTILS_BASE}/elink.fcgi"
    params = {
        "dbfrom": "gene",
        "db": "nucleotide",
        "id": entrez_id,
        "retmode": "xml"
    }

    if ENTREZ_API_KEY:
        params["api_key"] = ENTREZ_API_KEY

    logger.info(f"Fetching nucleotide IDs linked to Gene ID: {entrez_id}")

    data = await fetchWithRetry(url=url, session=session, params=params)

    if not data:
        logger.error(f"No nucleotide IDs found for Gene ID: {entrez_id}")
        return []

    try:
        root = ET.fromstring(data)
        nucl_ids = []

        # Parse linked IDs from XML
        for link in root.findall(".//Link/Id"):
            nucl_ids.append(link.text)

        logger.info(f"Found {len(nucl_ids)} nucleotide IDs for Gene ID: {entrez_id}")
        return nucl_ids
    except ET.ParseError as e:
        logger.error(f"Error parsing XML for nucleotide IDs: {str(e)}")
        return []

async def getSequence(nucl_id: str, session: RetryClient) -> Optional[Tuple[str, int, str]]:
    """
    Fetch sequence from NCBI Nucleotide database

    Args:
        nucl_id: Nucleotide accession ID
        session: RetryClient session

    Returns:
        Tuple of (sequence, length, accession) or None
    """
    url = f"{NCBI_EUTILS_BASE}/efetch.fcgi"
    params = {
        "db": "nucleotide",
        "id": nucl_id,
        "rettype": "fasta",
        "retmode": "text"
    }

    if ENTREZ_API_KEY:
        params["api_key"] = ENTREZ_API_KEY

    logger.info(f"Fetching sequence for Nucleotide ID: {nucl_id}")

    data = await fetchWithRetry(url=url, session=session, params=params)

    if not data:
        logger.error(f"No sequence found for Nucleotide ID: {nucl_id}")
        return None

    try:
        # Parse FASTA format
        lines = data.strip().split('\n')
        if len(lines) < 2:
            logger.warning(f"Invalid FASTA format for {nucl_id}")
            return None

        header = lines[0]
        sequence = ''.join(lines[1:])
        seq_len = len(sequence)

        logger.info(f"Sequence for {nucl_id}: {seq_len} bp")
        return sequence, seq_len, nucl_id
    except Exception as e:
        logger.error(f"Error parsing sequence for {nucl_id}: {str(e)}")
        return None

async def getSequenceByGeneID(entrez_id: int, session: RetryClient) -> Optional[Tuple[str, int, str]]:
    """
    Alternative method: Fetch sequence directly using gene ID
    This is useful for viral genes that might not have proper linking

    Args:
        entrez_id: NCBI Entrez Gene ID
        session: RetryClient session

    Returns:
        Tuple of (sequence, length, accession) or None
    """
    # First, try to get the gene info to find associated sequences
    url = f"{NCBI_EUTILS_BASE}/efetch.fcgi"
    params = {
        "db": "gene",
        "id": entrez_id,
        "rettype": "gene_fasta",
        "retmode": "text"
    }

    if ENTREZ_API_KEY:
        params["api_key"] = ENTREZ_API_KEY

    logger.info(f"Attempting direct sequence fetch for Gene ID: {entrez_id}")

    data = await fetchWithRetry(url=url, session=session, params=params)

    if data and data.strip():
        try:
            lines = data.strip().split('\n')
            if len(lines) >= 2 and lines[0].startswith('>'):
                sequence = ''.join(lines[1:])
                seq_len = len(sequence)
                logger.info(f"Direct fetch successful for Gene ID {entrez_id}: {seq_len} bp")
                return sequence, seq_len, str(entrez_id)
        except Exception as e:
            logger.error(f"Error parsing direct fetch for {entrez_id}: {str(e)}")

    return None

async def processViralGene(entrez_id: int, session: RetryClient) -> Tuple[Optional[str], Optional[str], int, Optional[str]]:
    """
    Process a viral gene Entrez ID and fetch its longest sequence

    Args:
        entrez_id: NCBI Entrez Gene ID
        session: RetryClient session

    Returns:
        Tuple of (gene_name, accession_id, sequence_length, sequence)
    """
    logger.info(f"Processing viral Gene Entrez ID: {entrez_id}")

    if stored_cache and entrez_id in stored_cache["Genes"]:
        logger.info(f"Using cached data for Entrez ID: {entrez_id}")
        return stored_cache["Genes"][entrez_id]

    # Get gene information
    gene_info = await getGeneInfo(entrez_id=entrez_id, session=session)
    gene_name = gene_info["gene_name"] if gene_info else None

    # Try to get linked nucleotide sequences
    nucl_ids = await getNucleotideIDs(entrez_id=entrez_id, session=session)

    max_seq_accession = None
    max_seq_len = 0
    max_seq = None

    if nucl_ids:
        logger.info(f"Analyzing {len(nucl_ids)} nucleotide sequences for Gene ID: {entrez_id}")

        for nucl_id in nucl_ids[:10]:  # Limit to first 10 to avoid excessive API calls
            result = await getSequence(nucl_id=nucl_id, session=session)

            if result:
                seq, seq_len, accession = result
                if seq_len > max_seq_len:
                    max_seq_accession = accession
                    max_seq_len = seq_len
                    max_seq = seq

            # Rate limiting for NCBI API (max 10 requests/second without API key, 3/second with key)
            await asyncio.sleep(0.15 if ENTREZ_API_KEY else 0.35)

    # If no sequences found through linking, try direct fetch
    if max_seq is None:
        logger.info(f"No linked sequences found, trying direct fetch for Gene ID: {entrez_id}")
        result = await getSequenceByGeneID(entrez_id=entrez_id, session=session)

        if result:
            max_seq, max_seq_len, max_seq_accession = result

    # Cache the result
    if stored_cache:
        stored_cache["Genes"][entrez_id] = (gene_name, max_seq_accession, max_seq_len, max_seq)

    return gene_name, max_seq_accession, max_seq_len, max_seq

async def process_row(row: pd.Series, session: RetryClient, semaphore: asyncio.Semaphore) -> dict:
    """
    Process a single row from the dataset

    Args:
        row: Pandas Series containing row data
        session: RetryClient session
        semaphore: Asyncio semaphore for concurrency control

    Returns:
        Dictionary with processed data
    """
    async with semaphore:
        logger.info(f"\n{"#"*100}\n\t\t Starting Row Processing\n{"#"*100}\n{row.to_string()}\n")

        # Extract data from row - adjust column names as needed for viral data
        entrez_id = int(row['Target Gene (Entrez ID)']) if not pd.isna(row['Target Gene (Entrez ID)']) else None
        miRNA = row['miRNA'] if not pd.isna(row['miRNA']) else None
        miRNATarBaseID = row.get('miRTarBase ID', None) if not pd.isna(row.get('miRTarBase ID', None)) else None
        targetGeneSymbol = row.get('Target Gene', None) if not pd.isna(row.get('Target Gene', None)) else None
        reference = int(row['References (PMID)']) if not pd.isna(row.get('References (PMID)', None)) else None

        # Handle missing critical data
        if miRNA is None or entrez_id is None:
            return {
                "miRTarBase ID": miRNATarBaseID,
                "miRNA": miRNA,
                "Gene Symbol": targetGeneSymbol,
                "Entrez ID": entrez_id,
                "Gene Name": None,
                "Nucleotide Accession": None,
                "miRNA Sequence Length": None,
                "Viral Sequence Length": None,
                "miRNA Sequence": None,
                "Viral Sequence": None,
                "Reference": reference
            }

        # Process the viral gene
        gene_name, seq_accession, seq_len, seq = await processViralGene(entrez_id=entrez_id, session=session)

        # Get miRNA sequence from database
        miRNA_seq, miRNA_seq_len = miRNA_db.get(miRNA, (None, None)) if miRNA_db else (None, None)

        return {
            "miRTarBase ID": miRNATarBaseID,
            "miRNA": miRNA,
            "Gene Symbol": targetGeneSymbol,
            "Entrez ID": entrez_id,
            "Gene Name": gene_name,
            "Nucleotide Accession": seq_accession,
            "miRNA Sequence Length": miRNA_seq_len,
            "Viral Sequence Length": seq_len,
            "miRNA Sequence": miRNA_seq,
            "Viral Sequence": seq,
            "Reference": reference
        }

async def process_chunk(chunk_df: pd.DataFrame):
    """
    Process a chunk of the dataframe asynchronously

    Args:
        chunk_df: Pandas DataFrame chunk

    Returns:
        List of processed results
    """
    retry_options = ExponentialRetry(
        attempts=10,
        max_timeout=50,
        statuses=[429, 500, 502, 503, 504],
        factor=2,
    )

    async with RetryClient(retry_options=retry_options) as session:
        # Lower concurrency limit for NCBI API to respect rate limits
        semaphore = asyncio.Semaphore(3 if ENTREZ_API_KEY else 2)
        tasks = [process_row(row, session, semaphore) for _, row in chunk_df.iterrows()]
        results = []

        for future in asyncio.as_completed(tasks):
            result = await future
            results.append(result)

        return results

def run_async_chunk(chunk: pd.DataFrame):
    """
    Wrapper to run async chunk processing

    Args:
        chunk: Pandas DataFrame chunk

    Returns:
        List of processed results
    """
    return asyncio.run(process_chunk(chunk))

def createChunks(df: pd.DataFrame, chunk_size: int) -> List[pd.DataFrame]:
    """
    Create chunks from dataframe

    Args:
        df: Pandas DataFrame
        chunk_size: Size of each chunk

    Returns:
        List of DataFrame chunks
    """
    n_chunks = chunk_size or cpu_count()
    logger.info(f"Creating chunks of size: {n_chunks}")
    return [df.iloc[i:i+n_chunks] for i in range(0, len(df), n_chunks)]

if __name__ == "__main__":
    # File paths - adjust as needed
    miRNA_path = "../Data/mature_mRNA_mirBase.fa"
    viral_data_path = "../Data/viral_mirTarbase.csv"  # Adjust to your viral dataset

    # IMPORTANT: Set your email for NCBI (required)
    ENTREZ_EMAIL = "your.email@example.com"  # CHANGE THIS!
    # Optional: Set API key for higher rate limits (get from https://www.ncbi.nlm.nih.gov/account/)
    # ENTREZ_API_KEY = "your_api_key_here"

    logger.info(f"Loading viral miRTarBase DataFrame from {viral_data_path}")

    try:
        mirBase_df = pd.read_csv(viral_data_path)
        # Adjust column processing based on your viral dataset structure
        if 'Experiments' in mirBase_df.columns:
            mirBase_df = mirBase_df.drop(columns=['Experiments'])
        if 'Support Type' in mirBase_df.columns:
            mirBase_df = mirBase_df.drop(columns=['Support Type'])

        mirBase_df = mirBase_df.drop_duplicates().reset_index(drop=True)
        logger.info(f"Loaded viral dataset with {len(mirBase_df)} rows after processing.")
    except FileNotFoundError:
        logger.error(f"File not found: {viral_data_path}")
        logger.info("Please ensure you have a CSV file with columns: 'miRNA', 'Target Gene (Entrez ID)', etc.")
        exit(1)

    # Adjust process count for API rate limits (NCBI is stricter than Ensembl)
    # Without API key: max 3 requests/second
    # With API key: max 10 requests/second
    number_of_processes = min(cpu_count(), 4)  # Limit to 4 processes for NCBI API
    logger.info(f"Number of Processes: {number_of_processes}")

    chunk_size = max(1, len(mirBase_df) // (number_of_processes * 2))

    manager = Manager()
    counter = manager.Value('i', 0)
    lock = manager.Lock()

    starting_count = 0
    with tqdm(total=len(mirBase_df), desc="Processing viral genes") as progress_bar:
        with Pool(processes=number_of_processes, initializer=init_process, initargs=(miRNA_path,)) as pool:
            results = []
            for result in pool.imap_unordered(run_async_chunk, createChunks(mirBase_df, chunk_size=chunk_size)):
                results.extend(result)
                with lock:
                    progress_bar.update(len(result))
                    starting_count += len(result)
                    print(f"Processed {colored(starting_count, 'green', attrs=['bold'])} "
                          f"out of {colored(len(mirBase_df), 'blue', attrs=['bold'])} viral genes")
                    logger.info(f"Processed {starting_count} out of {len(mirBase_df)} viral genes")

            final_df = pd.DataFrame(results)
            print("\nFinal Results:")
            print(final_df)

            output_path = "Data/viral_pipeline_results.csv"
            final_df.to_csv(output_path, index=False)
            logger.info(f"Results saved to {output_path}")
            print(f"\nResults saved to {colored(output_path, 'cyan', attrs=['bold'])}")

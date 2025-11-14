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
from typing import Optional, Tuple, Dict, List, Union
import xml.etree.ElementTree as ET
import re
from enum import Enum
from abc import ABC, abstractmethod

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

## ID Type Definitions and Patterns
class IDType(Enum):
    """Enumeration of supported ID types with their patterns and metadata"""
    ENTREZ = "entrez"
    GENBANK = "genbank"
    REFSEQ = "refseq"
    UNIPROT = "uniprot"
    ENSEMBL = "ensembl"
    EMBL = "embl"
    UNKNOWN = "unknown"

class IDPattern:
    """Regex patterns for different ID types"""
    PATTERNS = {
        IDType.ENTREZ: r'^\d+$',  # Pure numeric
        IDType.GENBANK: r'^[A-Z]{1,2}_?\d{5,}(\.\d+)?$',  # e.g., AB123456, AB_123456.1
        IDType.REFSEQ: r'^(NC|NG|NM|NP|NR|NT|NW|XM|XP|XR|YP|AP|NZ)_\d+(\.\d+)?$',  # RefSeq format
        IDType.UNIPROT: r'^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$',  # UniProt KB
        IDType.ENSEMBL: r'^ENS[A-Z]*[GPTR]\d{11}$',  # Ensembl format (ENSG, ENST, ENSP, etc.)
        IDType.EMBL: r'^[A-Z]{1,2}\d{5,}$',  # EMBL/ENA format
    }

    @classmethod
    def detect_id_type(cls, id_value: Union[str, int]) -> IDType:
        """
        Detect the type of ID based on its format

        Args:
            id_value: The ID to detect (can be string or int)

        Returns:
            IDType enum value
        """
        if id_value is None or (isinstance(id_value, float) and pd.isna(id_value)):
            return IDType.UNKNOWN

        # Convert to string for pattern matching
        id_str = str(id_value).strip()

        # Try each pattern
        for id_type, pattern in cls.PATTERNS.items():
            if re.match(pattern, id_str, re.IGNORECASE):
                return id_type

        return IDType.UNKNOWN

    @classmethod
    def validate_id(cls, id_value: Union[str, int], expected_type: IDType = None) -> bool:
        """
        Validate an ID against its expected type

        Args:
            id_value: The ID to validate
            expected_type: Expected IDType (if None, auto-detect)

        Returns:
            True if valid, False otherwise
        """
        detected_type = cls.detect_id_type(id_value)

        if expected_type is None:
            return detected_type != IDType.UNKNOWN

        return detected_type == expected_type

class DatabaseAdapter(ABC):
    """Abstract base class for database adapters"""

    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None):
        self.api_key = api_key
        self.email = email

    @abstractmethod
    async def get_gene_info(self, gene_id: Union[str, int], session: RetryClient) -> Optional[Dict]:
        """Fetch gene information"""
        pass

    @abstractmethod
    async def get_sequence_ids(self, gene_id: Union[str, int], session: RetryClient) -> List[str]:
        """Get linked sequence IDs"""
        pass

    @abstractmethod
    async def get_sequence(self, seq_id: str, session: RetryClient) -> Optional[Tuple[str, int, str]]:
        """Fetch sequence data"""
        pass

    @abstractmethod
    def get_rate_limit(self) -> float:
        """Get rate limit delay in seconds"""
        pass

class NCBIAdapter(DatabaseAdapter):
    """Adapter for NCBI databases - supports Entrez, GenBank, RefSeq IDs"""

    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None):
        super().__init__(api_key, email)
        self.base_url = NCBI_EUTILS_BASE

    def _prepare_params(self, params: dict) -> dict:
        """Add API key and email to parameters if available"""
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params

    async def get_gene_info(self, gene_id: Union[str, int], session: RetryClient) -> Optional[Dict]:
        """
        Fetch gene information from NCBI
        Supports Entrez IDs, GenBank IDs, and RefSeq IDs
        """
        id_type = IDPattern.detect_id_type(gene_id)

        # For Entrez IDs, use gene database
        if id_type == IDType.ENTREZ:
            return await self._get_gene_info_by_entrez(gene_id, session)

        # For GenBank/RefSeq, use nucleotide database
        elif id_type in [IDType.GENBANK, IDType.REFSEQ]:
            return await self._get_gene_info_by_accession(gene_id, session)

        else:
            logger.warning(f"Unsupported ID type for NCBI: {id_type} (ID: {gene_id})")
            return None

    async def _get_gene_info_by_entrez(self, entrez_id: int, session: RetryClient) -> Optional[Dict]:
        """Fetch gene info using Entrez ID"""
        url = f"{self.base_url}/esummary.fcgi"
        params = self._prepare_params({
            "db": "gene",
            "id": entrez_id,
            "retmode": "xml"
        })

        logger.info(f"Fetching gene info for Entrez ID: {entrez_id}")

        data = await fetchWithRetry(url=url, session=session, params=params)

        if not data:
            logger.error(f"No gene info found for Entrez ID: {entrez_id}")
            return None

        try:
            root = ET.fromstring(data)
            gene_name = None
            description = None

            for docsum in root.findall(".//DocumentSummary"):
                gene_name = docsum.findtext("Name")
                description = docsum.findtext("Description")

            logger.info(f"Gene info for {entrez_id}: {gene_name} - {description}")
            return {
                "gene_name": gene_name,
                "description": description,
                "gene_id": entrez_id,
                "id_type": IDType.ENTREZ.value
            }
        except ET.ParseError as e:
            logger.error(f"Error parsing XML for Entrez ID {entrez_id}: {str(e)}")
            return None

    async def _get_gene_info_by_accession(self, accession: str, session: RetryClient) -> Optional[Dict]:
        """Fetch gene info using GenBank/RefSeq accession"""
        url = f"{self.base_url}/esummary.fcgi"
        params = self._prepare_params({
            "db": "nucleotide",
            "id": accession,
            "retmode": "xml"
        })

        logger.info(f"Fetching sequence info for accession: {accession}")

        data = await fetchWithRetry(url=url, session=session, params=params)

        if not data:
            logger.error(f"No info found for accession: {accession}")
            return None

        try:
            root = ET.fromstring(data)
            gene_name = None
            description = None

            for docsum in root.findall(".//DocumentSummary"):
                description = docsum.findtext("Title")
                # Try to extract gene name from description
                gene_name = docsum.findtext("Caption")

            id_type = IDPattern.detect_id_type(accession)

            logger.info(f"Sequence info for {accession}: {gene_name} - {description}")
            return {
                "gene_name": gene_name,
                "description": description,
                "gene_id": accession,
                "id_type": id_type.value
            }
        except ET.ParseError as e:
            logger.error(f"Error parsing XML for accession {accession}: {str(e)}")
            return None

    async def get_sequence_ids(self, gene_id: Union[str, int], session: RetryClient) -> List[str]:
        """
        Get linked sequence IDs
        For Entrez IDs: use elink to find nucleotide sequences
        For GenBank/RefSeq: return the ID itself as it's already a sequence ID
        """
        id_type = IDPattern.detect_id_type(gene_id)

        # For accession numbers, return the ID itself
        if id_type in [IDType.GENBANK, IDType.REFSEQ]:
            logger.info(f"ID {gene_id} is already a sequence accession")
            return [str(gene_id)]

        # For Entrez IDs, use elink
        if id_type == IDType.ENTREZ:
            url = f"{self.base_url}/elink.fcgi"
            params = self._prepare_params({
                "dbfrom": "gene",
                "db": "nucleotide",
                "id": gene_id,
                "retmode": "xml"
            })

            logger.info(f"Fetching nucleotide IDs linked to Gene ID: {gene_id}")

            data = await fetchWithRetry(url=url, session=session, params=params)

            if not data:
                logger.error(f"No nucleotide IDs found for Gene ID: {gene_id}")
                return []

            try:
                root = ET.fromstring(data)
                nucl_ids = []

                for link in root.findall(".//Link/Id"):
                    nucl_ids.append(link.text)

                logger.info(f"Found {len(nucl_ids)} nucleotide IDs for Gene ID: {gene_id}")
                return nucl_ids
            except ET.ParseError as e:
                logger.error(f"Error parsing XML for nucleotide IDs: {str(e)}")
                return []

        return []

    async def get_sequence(self, seq_id: str, session: RetryClient) -> Optional[Tuple[str, int, str]]:
        """Fetch sequence from NCBI Nucleotide database"""
        url = f"{self.base_url}/efetch.fcgi"
        params = self._prepare_params({
            "db": "nucleotide",
            "id": seq_id,
            "rettype": "fasta",
            "retmode": "text"
        })

        logger.info(f"Fetching sequence for ID: {seq_id}")

        data = await fetchWithRetry(url=url, session=session, params=params)

        if not data:
            logger.error(f"No sequence found for ID: {seq_id}")
            return None

        try:
            lines = data.strip().split('\n')
            if len(lines) < 2:
                logger.warning(f"Invalid FASTA format for {seq_id}")
                return None

            header = lines[0]
            sequence = ''.join(lines[1:])
            seq_len = len(sequence)

            logger.info(f"Sequence for {seq_id}: {seq_len} bp")
            return sequence, seq_len, seq_id
        except Exception as e:
            logger.error(f"Error parsing sequence for {seq_id}: {str(e)}")
            return None

    def get_rate_limit(self) -> float:
        """Return rate limit delay for NCBI API"""
        # With API key: 10 req/sec (0.1s), without: 3 req/sec (0.35s)
        return 0.15 if self.api_key else 0.35

def get_adapter_for_id(id_value: Union[str, int], api_key: Optional[str] = None,
                       email: Optional[str] = None) -> Optional[DatabaseAdapter]:
    """
    Get the appropriate database adapter for a given ID

    Args:
        id_value: The ID to process
        api_key: Optional API key for the database
        email: Optional email for the database

    Returns:
        Appropriate DatabaseAdapter instance or None
    """
    id_type = IDPattern.detect_id_type(id_value)

    # Map ID types to adapters
    if id_type in [IDType.ENTREZ, IDType.GENBANK, IDType.REFSEQ]:
        return NCBIAdapter(api_key=api_key, email=email)
    elif id_type == IDType.ENSEMBL:
        logger.warning(f"Ensembl IDs not yet implemented for ID: {id_value}")
        return None
    elif id_type == IDType.UNIPROT:
        logger.warning(f"UniProt IDs not yet implemented for ID: {id_value}")
        return None
    else:
        logger.warning(f"Unknown ID type for ID: {id_value}")
        return None

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

async def processGeneID(gene_id: Union[str, int], session: RetryClient) -> Tuple[Optional[str], Optional[str], int, Optional[str], str]:
    """
    Process any type of gene ID and fetch its longest sequence
    Supports: Entrez IDs, GenBank IDs, RefSeq IDs, and more

    Args:
        gene_id: Gene ID (can be Entrez, GenBank, RefSeq, etc.)
        session: RetryClient session

    Returns:
        Tuple of (gene_name, accession_id, sequence_length, sequence, id_type)
    """
    # Detect ID type
    id_type = IDPattern.detect_id_type(gene_id)
    logger.info(f"Processing Gene ID: {gene_id} (detected type: {id_type.value})")

    # Create cache key that includes ID type
    cache_key = f"{id_type.value}:{gene_id}"

    if stored_cache and cache_key in stored_cache["Genes"]:
        logger.info(f"Using cached data for ID: {gene_id} (type: {id_type.value})")
        return stored_cache["Genes"][cache_key]

    # Get appropriate adapter for this ID type
    adapter = get_adapter_for_id(gene_id, api_key=ENTREZ_API_KEY, email=ENTREZ_EMAIL)

    if not adapter:
        logger.error(f"No adapter available for ID: {gene_id} (type: {id_type.value})")
        return None, None, 0, None, id_type.value

    # Get gene information
    gene_info = await adapter.get_gene_info(gene_id=gene_id, session=session)
    gene_name = gene_info["gene_name"] if gene_info else None

    # Get linked sequence IDs
    seq_ids = await adapter.get_sequence_ids(gene_id=gene_id, session=session)

    max_seq_accession = None
    max_seq_len = 0
    max_seq = None

    if seq_ids:
        logger.info(f"Analyzing {len(seq_ids)} sequences for Gene ID: {gene_id}")

        # Limit to first 10 to avoid excessive API calls
        for seq_id in seq_ids[:10]:
            result = await adapter.get_sequence(seq_id=seq_id, session=session)

            if result:
                seq, seq_len, accession = result
                if seq_len > max_seq_len:
                    max_seq_accession = accession
                    max_seq_len = seq_len
                    max_seq = seq

            # Rate limiting based on adapter
            await asyncio.sleep(adapter.get_rate_limit())

    # Cache the result with type-aware key
    if stored_cache:
        stored_cache["Genes"][cache_key] = (gene_name, max_seq_accession, max_seq_len, max_seq, id_type.value)

    return gene_name, max_seq_accession, max_seq_len, max_seq, id_type.value

async def process_row(row: pd.Series, session: RetryClient, semaphore: asyncio.Semaphore,
                     gene_id_column: str = 'Target Gene (Entrez ID)') -> dict:
    """
    Process a single row from the dataset
    Now supports ANY ID type (Entrez, GenBank, RefSeq, etc.)

    Args:
        row: Pandas Series containing row data
        session: RetryClient session
        semaphore: Asyncio semaphore for concurrency control
        gene_id_column: Name of the column containing gene IDs (default: 'Target Gene (Entrez ID)')

    Returns:
        Dictionary with processed data
    """
    async with semaphore:
        logger.info(f"\n{"#"*100}\n\t\t Starting Row Processing\n{"#"*100}\n{row.to_string()}\n")

        # Extract gene ID - support flexible column names
        gene_id = None
        if gene_id_column in row.index and not pd.isna(row[gene_id_column]):
            gene_id_raw = row[gene_id_column]
            # Try to preserve type (int vs string)
            id_type = IDPattern.detect_id_type(gene_id_raw)
            if id_type == IDType.ENTREZ:
                gene_id = int(gene_id_raw)
            else:
                gene_id = str(gene_id_raw).strip()

        # Extract other data from row
        miRNA = row['miRNA'] if not pd.isna(row['miRNA']) else None
        miRNATarBaseID = row.get('miRTarBase ID', None) if not pd.isna(row.get('miRTarBase ID', None)) else None
        targetGeneSymbol = row.get('Target Gene', None) if not pd.isna(row.get('Target Gene', None)) else None
        reference = int(row['References (PMID)']) if not pd.isna(row.get('References (PMID)', None)) else None

        # Handle missing critical data
        if miRNA is None or gene_id is None:
            return {
                "miRTarBase ID": miRNATarBaseID,
                "miRNA": miRNA,
                "Gene Symbol": targetGeneSymbol,
                "Gene ID": gene_id,
                "ID Type": IDPattern.detect_id_type(gene_id).value if gene_id else "unknown",
                "Gene Name": None,
                "Sequence Accession": None,
                "miRNA Sequence Length": None,
                "Target Sequence Length": None,
                "miRNA Sequence": None,
                "Target Sequence": None,
                "Reference": reference
            }

        # Process the gene ID (works with any ID type!)
        gene_name, seq_accession, seq_len, seq, detected_id_type = await processGeneID(gene_id=gene_id, session=session)

        # Get miRNA sequence from database
        miRNA_seq, miRNA_seq_len = miRNA_db.get(miRNA, (None, None)) if miRNA_db else (None, None)

        return {
            "miRTarBase ID": miRNATarBaseID,
            "miRNA": miRNA,
            "Gene Symbol": targetGeneSymbol,
            "Gene ID": gene_id,
            "ID Type": detected_id_type,
            "Gene Name": gene_name,
            "Sequence Accession": seq_accession,
            "miRNA Sequence Length": miRNA_seq_len,
            "Target Sequence Length": seq_len,
            "miRNA Sequence": miRNA_seq,
            "Target Sequence": seq,
            "Reference": reference
        }

def detect_gene_id_column(df: pd.DataFrame) -> Optional[str]:
    """
    Auto-detect the column containing gene IDs

    Args:
        df: Pandas DataFrame

    Returns:
        Column name or None
    """
    # Common column name patterns for gene IDs
    common_patterns = [
        r'.*gene.*id.*',
        r'.*entrez.*',
        r'.*genbank.*',
        r'.*refseq.*',
        r'.*accession.*',
        r'.*target.*id.*',
    ]

    for col in df.columns:
        col_lower = col.lower()
        for pattern in common_patterns:
            if re.match(pattern, col_lower, re.IGNORECASE):
                logger.info(f"Auto-detected gene ID column: {col}")
                return col

    logger.warning("Could not auto-detect gene ID column. Please specify manually.")
    return None

async def process_chunk(chunk_df: pd.DataFrame, gene_id_column: str = 'Target Gene (Entrez ID)'):
    """
    Process a chunk of the dataframe asynchronously
    Now supports any ID type with configurable column name

    Args:
        chunk_df: Pandas DataFrame chunk
        gene_id_column: Name of column containing gene IDs

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
        # Concurrency limit - can be adjusted based on API
        semaphore = asyncio.Semaphore(3 if ENTREZ_API_KEY else 2)
        tasks = [process_row(row, session, semaphore, gene_id_column) for _, row in chunk_df.iterrows()]
        results = []

        for future in asyncio.as_completed(tasks):
            result = await future
            results.append(result)

        return results

def run_async_chunk(args):
    """
    Wrapper to run async chunk processing
    Now accepts tuple of (chunk, gene_id_column)

    Args:
        args: Tuple of (chunk, gene_id_column)

    Returns:
        List of processed results
    """
    chunk, gene_id_column = args
    return asyncio.run(process_chunk(chunk, gene_id_column))

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
    # ==================== CONFIGURATION ====================
    # File paths - adjust as needed
    miRNA_path = "../Data/mature_mRNA_mirBase.fa"
    data_path = "../Data/viral_mirTarbase.csv"

    # IMPORTANT: Set your email for NCBI (required)
    ENTREZ_EMAIL = "your.email@example.com"  # CHANGE THIS!
    # Optional: Set API key for higher rate limits (get from https://www.ncbi.nlm.nih.gov/account/)
    # ENTREZ_API_KEY = "your_api_key_here"

    # Gene ID column configuration
    # Set to None for auto-detection, or specify the column name
    # Examples: 'Target Gene (Entrez ID)', 'GenBank Accession', 'RefSeq ID', etc.
    GENE_ID_COLUMN = None  # Auto-detect
    # GENE_ID_COLUMN = 'Target Gene (Entrez ID)'  # Explicit column name

    # Output file path
    OUTPUT_PATH = "Data/universal_pipeline_results.csv"
    # =======================================================

    logger.info(f"Loading miRTarBase DataFrame from {data_path}")
    logger.info("=" * 80)
    logger.info("UNIVERSAL ID PROCESSOR - Supports Entrez, GenBank, RefSeq, and more!")
    logger.info("=" * 80)

    try:
        mirBase_df = pd.read_csv(data_path)

        # Display available columns
        logger.info(f"Available columns: {list(mirBase_df.columns)}")

        # Auto-detect or validate gene ID column
        if GENE_ID_COLUMN is None:
            detected_column = detect_gene_id_column(mirBase_df)
            if detected_column:
                GENE_ID_COLUMN = detected_column
                logger.info(f"Using auto-detected column: {GENE_ID_COLUMN}")
            else:
                logger.error("Could not auto-detect gene ID column. Please specify GENE_ID_COLUMN manually.")
                logger.info(f"Available columns: {list(mirBase_df.columns)}")
                exit(1)
        else:
            if GENE_ID_COLUMN not in mirBase_df.columns:
                logger.error(f"Specified column '{GENE_ID_COLUMN}' not found in dataset.")
                logger.info(f"Available columns: {list(mirBase_df.columns)}")
                exit(1)
            logger.info(f"Using specified column: {GENE_ID_COLUMN}")

        # Analyze ID types in the dataset
        logger.info("Analyzing ID types in dataset...")
        sample_ids = mirBase_df[GENE_ID_COLUMN].dropna().head(10)
        id_type_counts = {}
        for sample_id in sample_ids:
            id_type = IDPattern.detect_id_type(sample_id)
            id_type_counts[id_type.value] = id_type_counts.get(id_type.value, 0) + 1
            logger.info(f"  Sample ID: {sample_id} -> Type: {id_type.value}")

        logger.info(f"ID type distribution in sample: {id_type_counts}")

        # Drop unnecessary columns if present
        if 'Experiments' in mirBase_df.columns:
            mirBase_df = mirBase_df.drop(columns=['Experiments'])
        if 'Support Type' in mirBase_df.columns:
            mirBase_df = mirBase_df.drop(columns=['Support Type'])

        mirBase_df = mirBase_df.drop_duplicates().reset_index(drop=True)
        logger.info(f"Loaded dataset with {len(mirBase_df)} rows after processing.")
    except FileNotFoundError:
        logger.error(f"File not found: {data_path}")
        logger.info("Please ensure you have a CSV file with columns: 'miRNA', gene ID column, etc.")
        exit(1)

    # Adjust process count for API rate limits
    # NCBI: Without API key: max 3 requests/second, With API key: max 10 requests/second
    number_of_processes = min(cpu_count(), 4)
    logger.info(f"Number of Processes: {number_of_processes}")

    chunk_size = max(1, len(mirBase_df) // (number_of_processes * 2))

    manager = Manager()
    counter = manager.Value('i', 0)
    lock = manager.Lock()

    starting_count = 0
    with tqdm(total=len(mirBase_df), desc="Processing genes (any ID type)") as progress_bar:
        with Pool(processes=number_of_processes, initializer=init_process, initargs=(miRNA_path,)) as pool:
            results = []
            # Create argument tuples with gene_id_column
            chunk_args = [(chunk, GENE_ID_COLUMN) for chunk in createChunks(mirBase_df, chunk_size=chunk_size)]

            for result in pool.imap_unordered(run_async_chunk, chunk_args):
                results.extend(result)
                with lock:
                    progress_bar.update(len(result))
                    starting_count += len(result)
                    print(f"Processed {colored(starting_count, 'green', attrs=['bold'])} "
                          f"out of {colored(len(mirBase_df), 'blue', attrs=['bold'])} genes")
                    logger.info(f"Processed {starting_count} out of {len(mirBase_df)} genes")

            final_df = pd.DataFrame(results)
            print("\nFinal Results:")
            print(final_df)

            final_df.to_csv(OUTPUT_PATH, index=False)
            logger.info(f"Results saved to {OUTPUT_PATH}")
            print(f"\nResults saved to {colored(OUTPUT_PATH, 'cyan', attrs=['bold'])}")

            # Display ID type statistics
            if 'ID Type' in final_df.columns:
                id_type_stats = final_df['ID Type'].value_counts()
                print(f"\n{colored('ID Type Statistics:', 'yellow', attrs=['bold'])}")
                for id_type, count in id_type_stats.items():
                    print(f"  {id_type}: {colored(count, 'cyan', attrs=['bold'])}")
                logger.info(f"ID type statistics: {id_type_stats.to_dict()}")

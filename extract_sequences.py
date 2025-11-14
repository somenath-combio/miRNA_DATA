#!/usr/bin/env python3
"""
Extract miRNA and mRNA sequences from ViRBase data.

This script:
1. Reads the Virbase_3.0_ready.xlsx file
2. Extracts miRNA sequences from a FASTA file
3. Fetches mRNA sequences from NCBI for various ID types (Entrez, GenBank, RefSeq)
"""

import pandas as pd
import re
import time
from typing import Dict, List, Tuple, Optional
from Bio import Entrez, SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure Entrez
Entrez.email = "your.email@example.com"  # CHANGE THIS TO YOUR EMAIL
Entrez.api_key = None  # Optional: Add your NCBI API key for faster access


class IDClassifier:
    """Classify different types of biological sequence IDs."""

    @staticmethod
    def classify_id(id_str: str) -> str:
        """
        Classify an ID into its type.

        Returns: 'genbank', 'refseq', 'numeric', or 'unknown'
        """
        id_str = str(id_str).strip()

        # RefSeq patterns (NC_, NM_, NR_, XM_, XR_, etc.)
        if re.match(r'^[NX][CGMRW]_\d+(\.\d+)?$', id_str):
            return 'refseq'

        # GenBank accession patterns
        if re.match(r'^[A-Z]{1,2}\d{5,6}(\.\d+)?$', id_str):
            return 'genbank'

        # Numeric IDs (Entrez Gene ID or GI)
        if re.match(r'^\d+$', id_str):
            return 'numeric'

        return 'unknown'


class SequenceFetcher:
    """Fetch sequences from NCBI."""

    def __init__(self, email: str, api_key: Optional[str] = None, retry_delay: int = 2):
        """
        Initialize the sequence fetcher.

        Args:
            email: Your email for NCBI Entrez
            api_key: Optional NCBI API key
            retry_delay: Delay between retries (seconds)
        """
        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
        self.retry_delay = retry_delay
        self.classifier = IDClassifier()

    def fetch_sequence(self, id_str: str, max_retries: int = 3) -> Optional[SeqRecord]:
        """
        Fetch sequence for any ID type.

        Args:
            id_str: The ID to fetch
            max_retries: Maximum number of retry attempts

        Returns:
            SeqRecord object or None if fetch fails
        """
        id_type = self.classifier.classify_id(id_str)
        logger.info(f"Fetching {id_str} (type: {id_type})")

        if id_type == 'genbank' or id_type == 'refseq':
            return self._fetch_by_accession(id_str, max_retries)
        elif id_type == 'numeric':
            # Try as Entrez Gene ID first, then as nucleotide ID
            seq = self._fetch_by_gene_id(id_str, max_retries)
            if seq is None:
                seq = self._fetch_by_nucleotide_id(id_str, max_retries)
            return seq
        else:
            logger.warning(f"Unknown ID type for {id_str}")
            return None

    def _fetch_by_accession(self, accession: str, max_retries: int) -> Optional[SeqRecord]:
        """Fetch sequence by GenBank/RefSeq accession."""
        for attempt in range(max_retries):
            try:
                handle = Entrez.efetch(
                    db="nucleotide",
                    id=accession,
                    rettype="fasta",
                    retmode="text"
                )
                record = SeqIO.read(handle, "fasta")
                handle.close()
                logger.info(f"Successfully fetched {accession}")
                return record
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {accession}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.retry_delay)

        logger.error(f"Failed to fetch {accession} after {max_retries} attempts")
        return None

    def _fetch_by_gene_id(self, gene_id: str, max_retries: int) -> Optional[SeqRecord]:
        """Fetch sequence by Entrez Gene ID (tries to get mRNA sequence)."""
        for attempt in range(max_retries):
            try:
                # Search for linked nucleotide sequences
                link_handle = Entrez.elink(
                    dbfrom="gene",
                    db="nucleotide",
                    id=gene_id,
                    linkname="gene_nuccore_refseqrna"
                )
                link_results = Entrez.read(link_handle)
                link_handle.close()

                if link_results[0]["LinkSetDb"]:
                    # Get the first linked nucleotide ID
                    nuc_id = link_results[0]["LinkSetDb"][0]["Link"][0]["Id"]

                    # Fetch the sequence
                    fetch_handle = Entrez.efetch(
                        db="nucleotide",
                        id=nuc_id,
                        rettype="fasta",
                        retmode="text"
                    )
                    record = SeqIO.read(fetch_handle, "fasta")
                    fetch_handle.close()
                    logger.info(f"Successfully fetched gene {gene_id} -> {nuc_id}")
                    return record
                else:
                    logger.warning(f"No RefSeq mRNA found for gene ID {gene_id}")
                    return None

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for gene ID {gene_id}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.retry_delay)

        logger.error(f"Failed to fetch gene ID {gene_id} after {max_retries} attempts")
        return None

    def _fetch_by_nucleotide_id(self, nuc_id: str, max_retries: int) -> Optional[SeqRecord]:
        """Fetch sequence by nucleotide database ID."""
        for attempt in range(max_retries):
            try:
                handle = Entrez.efetch(
                    db="nucleotide",
                    id=nuc_id,
                    rettype="fasta",
                    retmode="text"
                )
                record = SeqIO.read(handle, "fasta")
                handle.close()
                logger.info(f"Successfully fetched nucleotide ID {nuc_id}")
                return record
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for nucleotide ID {nuc_id}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.retry_delay)

        logger.error(f"Failed to fetch nucleotide ID {nuc_id} after {max_retries} attempts")
        return None


class miRNAExtractor:
    """Extract miRNA sequences from FASTA file."""

    @staticmethod
    def extract_mirna_sequences(fasta_file: str, mirna_ids: List[str]) -> Dict[str, SeqRecord]:
        """
        Extract miRNA sequences from a FASTA file.

        Args:
            fasta_file: Path to miRNA FASTA file
            mirna_ids: List of miRNA IDs to extract

        Returns:
            Dictionary mapping miRNA ID to SeqRecord
        """
        mirna_dict = {}
        mirna_ids_set = set(str(mid).strip() for mid in mirna_ids)

        logger.info(f"Reading miRNA FASTA file: {fasta_file}")
        try:
            for record in SeqIO.parse(fasta_file, "fasta"):
                # Check if any miRNA ID is in the record ID or description
                for mirna_id in mirna_ids_set:
                    if mirna_id in record.id or mirna_id in record.description:
                        mirna_dict[mirna_id] = record
                        logger.info(f"Found miRNA: {mirna_id}")
                        break

            logger.info(f"Extracted {len(mirna_dict)} miRNA sequences")
            return mirna_dict
        except Exception as e:
            logger.error(f"Error reading miRNA FASTA file: {e}")
            return {}


def main():
    """Main execution function."""

    # Configuration
    EXCEL_FILE = "Virbase_3.0_ready.xlsx"
    MIRNA_FASTA = "mirna.fasta"  # CHANGE THIS TO YOUR miRNA FASTA FILE PATH
    OUTPUT_MIRNA = "extracted_mirna_sequences.fasta"
    OUTPUT_MRNA = "extracted_mrna_sequences.fasta"
    OUTPUT_REPORT = "extraction_report.txt"
    EMAIL = "your.email@example.com"  # CHANGE THIS TO YOUR EMAIL

    logger.info("="*80)
    logger.info("Starting sequence extraction")
    logger.info("="*80)

    # Read Excel file
    logger.info(f"Reading Excel file: {EXCEL_FILE}")
    df = pd.read_excel(EXCEL_FILE)
    logger.info(f"Loaded {len(df)} rows")

    # Get unique IDs
    unique_mirna_ids = df['miRNA ID'].dropna().unique().tolist()
    unique_mrna_ids = df['Entrez ID'].dropna().astype(str).unique().tolist()

    logger.info(f"Found {len(unique_mirna_ids)} unique miRNA IDs")
    logger.info(f"Found {len(unique_mrna_ids)} unique mRNA/gene IDs")

    # Extract miRNA sequences
    logger.info("\n" + "="*80)
    logger.info("Extracting miRNA sequences")
    logger.info("="*80)
    mirna_extractor = miRNAExtractor()
    mirna_sequences = mirna_extractor.extract_mirna_sequences(MIRNA_FASTA, unique_mirna_ids)

    # Save miRNA sequences
    if mirna_sequences:
        SeqIO.write(mirna_sequences.values(), OUTPUT_MIRNA, "fasta")
        logger.info(f"Saved {len(mirna_sequences)} miRNA sequences to {OUTPUT_MIRNA}")

    # Fetch mRNA sequences
    logger.info("\n" + "="*80)
    logger.info("Fetching mRNA sequences from NCBI")
    logger.info("="*80)
    fetcher = SequenceFetcher(email=EMAIL)
    mrna_sequences = {}
    failed_ids = []

    for idx, mrna_id in enumerate(unique_mrna_ids, 1):
        logger.info(f"Processing {idx}/{len(unique_mrna_ids)}: {mrna_id}")
        seq = fetcher.fetch_sequence(mrna_id)
        if seq:
            mrna_sequences[mrna_id] = seq
        else:
            failed_ids.append(mrna_id)

        # Be nice to NCBI servers
        time.sleep(0.4)  # Max 3 requests per second without API key

    # Save mRNA sequences
    if mrna_sequences:
        SeqIO.write(mrna_sequences.values(), OUTPUT_MRNA, "fasta")
        logger.info(f"Saved {len(mrna_sequences)} mRNA sequences to {OUTPUT_MRNA}")

    # Generate report
    logger.info("\n" + "="*80)
    logger.info("Generating extraction report")
    logger.info("="*80)

    with open(OUTPUT_REPORT, 'w') as f:
        f.write("Sequence Extraction Report\n")
        f.write("="*80 + "\n\n")

        f.write(f"Input file: {EXCEL_FILE}\n")
        f.write(f"Total rows: {len(df)}\n\n")

        f.write("miRNA Extraction:\n")
        f.write(f"  Unique miRNA IDs: {len(unique_mirna_ids)}\n")
        f.write(f"  Sequences extracted: {len(mirna_sequences)}\n")
        f.write(f"  Missing: {len(unique_mirna_ids) - len(mirna_sequences)}\n\n")

        f.write("mRNA Extraction:\n")
        f.write(f"  Unique mRNA/gene IDs: {len(unique_mrna_ids)}\n")
        f.write(f"  Sequences fetched: {len(mrna_sequences)}\n")
        f.write(f"  Failed: {len(failed_ids)}\n\n")

        if failed_ids:
            f.write("Failed IDs:\n")
            for fid in failed_ids:
                f.write(f"  - {fid}\n")

    logger.info(f"Report saved to {OUTPUT_REPORT}")
    logger.info("\n" + "="*80)
    logger.info("Extraction complete!")
    logger.info("="*80)
    logger.info(f"miRNA sequences: {OUTPUT_MIRNA}")
    logger.info(f"mRNA sequences: {OUTPUT_MRNA}")
    logger.info(f"Report: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()

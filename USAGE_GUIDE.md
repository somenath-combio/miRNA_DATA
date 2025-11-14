# miRNA and mRNA Sequence Extraction Guide

## Overview
This script extracts miRNA and mRNA sequences from the ViRBase 3.0 dataset. It handles multiple ID types including:
- **miRNA IDs**: MIMAT accessions from miRBase
- **mRNA/Gene IDs**: Entrez Gene IDs, GenBank accessions, RefSeq accessions

## Prerequisites

### 1. Install Required Packages
```bash
pip install -r requirements.txt
```

### 2. Prepare Your Files
- `Virbase_3.0_ready.xlsx` - The ViRBase data file
- `mirna.fasta` - Your miRNA FASTA file (change the filename in the script if different)

### 3. Configure the Script
Edit `extract_sequences.py` and update these variables:

```python
# Line 220-225
MIRNA_FASTA = "mirna.fasta"  # Change to your miRNA FASTA file path
EMAIL = "your.email@example.com"  # CHANGE THIS TO YOUR EMAIL (required by NCBI)
```

**Important**: You MUST provide a valid email address. NCBI requires this to contact you if there are issues with your queries.

### 4. Optional: Get NCBI API Key (Recommended)
- Visit: https://www.ncbi.nlm.nih.gov/account/
- Create an account and generate an API key
- Add it to the script (line 218):
```python
Entrez.api_key = "your_api_key_here"
```

With an API key, you can make 10 requests/second instead of 3.

## Usage

### Basic Usage
```bash
python3 extract_sequences.py
```

### What It Does
1. Reads the Excel file `Virbase_3.0_ready.xlsx`
2. Extracts unique miRNA IDs and mRNA/gene IDs
3. Extracts miRNA sequences from your FASTA file
4. Fetches mRNA sequences from NCBI (handles multiple ID types automatically)
5. Saves results to FASTA files
6. Generates a detailed report

### Output Files
- `extracted_mirna_sequences.fasta` - miRNA sequences
- `extracted_mrna_sequences.fasta` - mRNA sequences
- `extraction_report.txt` - Detailed extraction report

## ID Types Handled

The script automatically detects and handles:

### 1. RefSeq Accessions
Format: `NC_045512.2`, `NM_001301717.1`, `XM_024447171.1`
- NC_* : Reference chromosomes
- NM_* : mRNA sequences
- NR_* : Non-coding RNA
- XM_* : Predicted mRNA
- XR_* : Predicted non-coding RNA

### 2. GenBank Accessions
Format: `MT576563.1`, `AY394850.2`, `KT326819.1`
- 1-2 letters followed by 5-6 digits
- Optional version number (`.1`, `.2`, etc.)

### 3. Numeric IDs
Format: `1489672`, `43740578`
- Entrez Gene IDs
- GenBank GI numbers (legacy)

The script tries multiple strategies for numeric IDs:
1. First as Entrez Gene ID → finds linked RefSeq mRNA
2. Then as nucleotide database ID

## Examples

### Example 1: Default Run
```bash
# Make sure your files are in place
ls Virbase_3.0_ready.xlsx mirna.fasta

# Run the extraction
python3 extract_sequences.py
```

### Example 2: Checking Progress
The script provides detailed logging output:
```
2025-11-14 10:30:15 - INFO - Starting sequence extraction
2025-11-14 10:30:16 - INFO - Loaded 5195 rows
2025-11-14 10:30:16 - INFO - Found 484 unique miRNA IDs
2025-11-14 10:30:16 - INFO - Found 72 unique mRNA/gene IDs
2025-11-14 10:30:17 - INFO - Fetching NC_045512.2 (type: refseq)
2025-11-14 10:30:18 - INFO - Successfully fetched NC_045512.2
...
```

### Example 3: View Results
```bash
# Check how many sequences were extracted
grep -c "^>" extracted_mirna_sequences.fasta
grep -c "^>" extracted_mrna_sequences.fasta

# View the report
cat extraction_report.txt
```

## Troubleshooting

### Issue: "ModuleNotFoundError"
**Solution**: Install required packages
```bash
pip install pandas openpyxl biopython
```

### Issue: "HTTPError 429 - Too Many Requests"
**Solution**: 
1. Get an NCBI API key (see step 4 above)
2. Or reduce request rate by increasing sleep time in line 285:
```python
time.sleep(1.0)  # Increase from 0.4 to 1.0 second
```

### Issue: "No sequences found for miRNA"
**Solution**: 
1. Check that your miRNA FASTA file path is correct
2. Verify that the miRNA IDs in the FASTA file match those in the Excel file
3. Try opening the FASTA file and checking the header format

### Issue: "Failed to fetch" some mRNA IDs
**Solution**: This is normal. Some IDs may be:
- Outdated or deprecated
- Not available in NCBI databases
- Incorrectly formatted

Check the `extraction_report.txt` for a list of failed IDs.

## Performance Notes

- **Without API key**: ~3 requests/second = ~24 seconds for 72 IDs
- **With API key**: ~10 requests/second = ~7 seconds for 72 IDs
- miRNA extraction is instant (local file parsing)
- Total time depends on number of unique IDs

## NCBI Usage Policy

- Always provide a valid email address
- Respect rate limits (3 req/s without API key, 10 req/s with key)
- Do not make parallel requests without an API key
- For large-scale extractions (>1000 IDs), use an API key

## Advanced Usage

### Modify Output File Names
Edit lines 220-223 in `extract_sequences.py`:
```python
OUTPUT_MIRNA = "my_mirna.fasta"
OUTPUT_MRNA = "my_mrna.fasta"
OUTPUT_REPORT = "my_report.txt"
```

### Adjust Retry Logic
Edit line 142 in the `SequenceFetcher.__init__()`:
```python
self.retry_delay = 5  # Wait 5 seconds between retries
```

### Extract Specific Rows Only
Modify the script to filter the DataFrame:
```python
# After line 230, add:
df = df[df['Score'] > 0.5]  # Only high-confidence interactions
```

## Support

For issues with:
- **Script bugs**: Check the log output and error messages
- **NCBI connection**: Verify your email and check NCBI status
- **Missing sequences**: Check the extraction report for details

## Citation

If you use this script, please cite:
- ViRBase: http://www.rna-society.org/virbase/
- NCBI Entrez: https://www.ncbi.nlm.nih.gov/
- Biopython: Cock et al. (2009) Bioinformatics

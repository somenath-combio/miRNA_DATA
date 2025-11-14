# miRNA and mRNA Sequence Extraction Tool

Extract miRNA and mRNA sequences from ViRBase 3.0 data with support for multiple ID types.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Edit the script configuration (lines 220-225)
nano extract_sequences.py
# Update: MIRNA_FASTA path and EMAIL address

# 3. Run extraction
python3 extract_sequences.py
```

## Features

✅ **Multi-ID Type Support**
- Entrez Gene IDs (numeric)
- GenBank accessions (e.g., MT576563.1)
- RefSeq accessions (e.g., NC_045512.2)
- Automatically detects and handles each type

✅ **Robust Fetching**
- Automatic retry on failures
- Rate limiting for NCBI compliance
- Detailed logging and error reporting

✅ **Comprehensive Output**
- miRNA sequences (from your FASTA file)
- mRNA sequences (fetched from NCBI)
- Detailed extraction report

## Output Files

- `extracted_mirna_sequences.fasta` - All miRNA sequences
- `extracted_mrna_sequences.fasta` - All mRNA sequences  
- `extraction_report.txt` - Statistics and failed IDs

## Requirements

- Python 3.7+
- Internet connection (for NCBI fetching)
- Valid email address (NCBI requirement)

## Documentation

See `USAGE_GUIDE.md` for detailed instructions, troubleshooting, and advanced usage.

## ID Type Detection

The script automatically identifies:

| ID Example | Type | Database |
|------------|------|----------|
| 1489672 | Numeric | Entrez Gene / Nucleotide |
| NC_045512.2 | RefSeq | NCBI RefSeq |
| MT576563.1 | GenBank | NCBI GenBank |

## Performance

- 72 unique mRNA IDs: ~24 seconds (without API key)
- 484 unique miRNA IDs: <1 second (local file)

Get an NCBI API key for 3x faster fetching!

## Important Notes

⚠️ **Must configure before running:**
1. Set your email address in the script
2. Update the miRNA FASTA file path
3. Ensure `Virbase_3.0_ready.xlsx` is in the same directory

📧 **NCBI Policy**: A valid email is required by NCBI. They use it only to contact you if there are issues with your queries.

## Support

For questions or issues, check `USAGE_GUIDE.md` or review the log output.

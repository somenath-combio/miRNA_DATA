# Viral Entrez ID Fetcher

This is a rewritten version of the miRNA-target interaction fetcher, adapted specifically for **viral Entrez IDs**.

## Key Differences from Human Version

### 1. **API Change: Ensembl → NCBI Entrez**

| Aspect | Human Version | Viral Version |
|--------|--------------|---------------|
| **Primary API** | Ensembl REST API | NCBI E-utilities (Entrez) |
| **Gene Database** | Ensembl Gene IDs | NCBI Gene (Entrez) |
| **Sequence Database** | Ensembl Transcripts | NCBI Nucleotide |
| **Data Format** | JSON | XML/FASTA |

**Why this change?**
- Ensembl focuses on eukaryotic genomes (human, mouse, etc.)
- NCBI has comprehensive viral genome data
- Viral genes don't have Ensembl Gene IDs

### 2. **Sequence Fetching Strategy**

**Human Version:**
```
Entrez ID → Ensembl Gene ID → Transcript IDs → Sequences
```

**Viral Version:**
```
Entrez ID → Nucleotide IDs → Sequences
            ↓
        (fallback: direct gene fetch)
```

### 3. **Rate Limiting**

| Feature | Human (Ensembl) | Viral (NCBI) |
|---------|----------------|--------------|
| **Rate Limit** | ~15 req/sec | 3 req/sec (no key)<br>10 req/sec (with key) |
| **Concurrency** | 100 | 2-3 |
| **API Key** | Not required | Recommended |

### 4. **Output Columns**

**Changed Columns:**
- `Ensembl Gene ID` → `Gene Name`
- `Ensembl Transcript ID` → `Nucleotide Accession`
- `mRNA Sequence Length` → `Viral Sequence Length`
- `mRNA Sequence` → `Viral Sequence`

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. **IMPORTANT: Set Your Email**

NCBI requires an email address for API usage. Edit the file:

```python
# Line ~16 in viral_entrez_fetcher.py
ENTREZ_EMAIL = "your.email@example.com"  # CHANGE THIS!
```

### 3. (Optional) Get NCBI API Key

For higher rate limits (10 req/sec vs 3 req/sec):
1. Create account at https://www.ncbi.nlm.nih.gov/account/
2. Get API key from account settings
3. Set it in the code:
```python
ENTREZ_API_KEY = "your_api_key_here"
```

## Usage

### Input Data Format

The script expects a CSV file with at least these columns:
- `miRNA`: miRNA identifier
- `Target Gene (Entrez ID)`: **Viral** gene Entrez ID
- `Target Gene`: Gene symbol (optional)
- `References (PMID)`: PubMed ID (optional)
- `miRTarBase ID`: Interaction ID (optional)

### Running the Script

```bash
python viral_entrez_fetcher.py
```

### Configuration

Edit these variables in the `__main__` section:

```python
miRNA_path = "../Data/mature_mRNA_mirBase.fa"     # Path to miRNA FASTA
viral_data_path = "../Data/viral_mirTarbase.csv"  # Path to viral dataset
```

## How It Works

### 1. Gene Information Retrieval
```
NCBI EUtils API → ESummary → Gene Info (name, description)
```

### 2. Nucleotide Sequence Discovery
```
NCBI EUtils API → ELink → Gene → Nucleotide database
```

### 3. Sequence Fetching
```
NCBI EUtils API → EFetch → FASTA format sequences
```

### 4. Fallback Strategy
If no linked sequences found:
```
Direct fetch from Gene database → gene_fasta format
```

## Performance Considerations

### Human Version
- **Processes**: CPU count × 4
- **Concurrency**: 100 parallel API calls
- **Rate**: Very fast (Ensembl is permissive)

### Viral Version
- **Processes**: min(CPU count, 4)
- **Concurrency**: 2-3 parallel API calls
- **Rate**: Slower (NCBI rate limits)
- **Sleep**: 0.35s between calls (0.15s with API key)

**Estimated Time:**
- 100 viral genes: ~30-60 minutes (without API key)
- 100 viral genes: ~15-30 minutes (with API key)

## Example Output

```csv
miRTarBase ID,miRNA,Gene Symbol,Entrez ID,Gene Name,Nucleotide Accession,miRNA Sequence Length,Viral Sequence Length,miRNA Sequence,Viral Sequence,Reference
MIRT001,hsa-miR-21,VP1,12345678,VP1,NC_001234.1,22,7500,TAGCTTATCAGACTGATGTTGA,ATGGATCCG...,28945678
```

## Troubleshooting

### 1. "Email parameter required"
→ Set `ENTREZ_EMAIL` in the code

### 2. "Rate limit exceeded"
→ Reduce `number_of_processes` or add `ENTREZ_API_KEY`

### 3. "No sequences found"
→ Check if Entrez IDs are valid viral gene IDs
→ Try searching manually at https://www.ncbi.nlm.nih.gov/gene/

### 4. Slow performance
→ Get an NCBI API key for 3× speed improvement

## API Endpoints Used

1. **ESummary** - Gene information
   ```
   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id=...
   ```

2. **ELink** - Find linked nucleotide sequences
   ```
   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=gene&db=nucleotide&id=...
   ```

3. **EFetch** - Retrieve sequences
   ```
   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nucleotide&id=...&rettype=fasta
   ```

## References

- [NCBI E-utilities Documentation](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [Biopython Entrez Module](https://biopython.org/docs/1.75/api/Bio.Entrez.html)
- [NCBI Rate Limits](https://www.ncbi.nlm.nih.gov/books/NBK25497/#chapter2.Usage_Guidelines_and_Requiremen)

## License

Same as original code.

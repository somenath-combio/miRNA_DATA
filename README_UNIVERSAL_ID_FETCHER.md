# Universal Gene ID Fetcher

**NEW!** This script now supports **ANY type of gene ID** - Entrez, GenBank, RefSeq, and more!

## What's New: Universal ID Support

The script has been completely refactored to work with multiple ID types automatically:

### Supported ID Types

| ID Type | Format Examples | Database | Status |
|---------|----------------|----------|--------|
| **Entrez** | `12345`, `54321` | NCBI Gene | ✅ Fully Supported |
| **GenBank** | `AB123456`, `AB_123456.1` | NCBI Nucleotide | ✅ Fully Supported |
| **RefSeq** | `NC_001234.1`, `NM_001234.5` | NCBI RefSeq | ✅ Fully Supported |
| **UniProt** | `P12345`, `Q9Y6K9` | UniProt KB | 🔄 Pattern Ready* |
| **Ensembl** | `ENSG00000139618` | Ensembl | 🔄 Pattern Ready* |
| **EMBL** | `AJ123456` | EMBL/ENA | 🔄 Pattern Ready* |

\* *Pattern detection ready, adapter implementation in progress*

### Key Features

✨ **Auto-Detection**
- Automatically detects ID type from format
- No need to specify what type of ID you're using!

✨ **Flexible Column Names**
- Auto-detects gene ID columns
- Or specify your own column name

✨ **Mixed ID Types**
- Can process datasets with multiple ID types
- Tracks ID type for each entry

✨ **Type-Aware Caching**
- Prevents cache collisions between different ID types
- Faster processing for repeated IDs

## Quick Start

### 1. Installation

```bash
pip install -r requirements.txt
```

### 2. Configure Your Data

Edit the configuration section in `viral_entrez_fetcher.py`:

```python
# ==================== CONFIGURATION ====================
miRNA_path = "../Data/mature_mRNA_mirBase.fa"
data_path = "../Data/your_dataset.csv"

# IMPORTANT: Set your email for NCBI (required)
ENTREZ_EMAIL = "your.email@example.com"  # CHANGE THIS!

# Optional: Get API key for faster processing
# ENTREZ_API_KEY = "your_api_key_here"

# Gene ID column - set to None for auto-detection
GENE_ID_COLUMN = None  # Auto-detect
# Or specify explicitly:
# GENE_ID_COLUMN = 'Target Gene (Entrez ID)'
# GENE_ID_COLUMN = 'GenBank Accession'
# GENE_ID_COLUMN = 'RefSeq ID'

OUTPUT_PATH = "Data/universal_pipeline_results.csv"
# =======================================================
```

### 3. Run the Script

```bash
python viral_entrez_fetcher.py
```

## Usage Examples

### Example 1: Dataset with Entrez IDs

Your CSV has a column `Target Gene (Entrez ID)`:
```csv
miRNA,Target Gene (Entrez ID),Target Gene
hsa-miR-21,12345,GENE1
hsa-miR-155,54321,GENE2
```

**Config:**
```python
GENE_ID_COLUMN = None  # Auto-detect will find it!
```

### Example 2: Dataset with GenBank Accessions

Your CSV has a column `GenBank Accession`:
```csv
miRNA,GenBank Accession,Target Gene
hsa-miR-21,AB123456.1,GENE1
hsa-miR-155,NC_001234.2,GENE2
```

**Config:**
```python
GENE_ID_COLUMN = None  # Auto-detect works here too!
# Or be explicit:
# GENE_ID_COLUMN = 'GenBank Accession'
```

### Example 3: Dataset with RefSeq IDs

Your CSV has RefSeq nucleotide IDs:
```csv
miRNA,RefSeq ID,Target Gene
hsa-miR-21,NM_001234.5,GENE1
hsa-miR-155,NC_045512.2,SARS-CoV-2
```

**Config:**
```python
GENE_ID_COLUMN = 'RefSeq ID'  # Specify the column
```

### Example 4: Mixed ID Types

Your dataset has **different types of IDs**:
```csv
miRNA,Gene ID,Target Gene
hsa-miR-21,12345,GENE1
hsa-miR-155,NC_001234.2,Viral Gene
hsa-miR-29,AB123456,Another Gene
```

The script automatically detects each ID type and processes accordingly!

## How It Works

### 1. ID Type Detection

The script uses regex patterns to detect ID types:

```python
# Automatic detection
id_type = IDPattern.detect_id_type("NC_001234.2")
# Returns: IDType.REFSEQ

id_type = IDPattern.detect_id_type("12345")
# Returns: IDType.ENTREZ

id_type = IDPattern.detect_id_type("AB123456.1")
# Returns: IDType.GENBANK
```

### 2. Database Adapter Selection

Based on the detected ID type, the appropriate adapter is selected:

```
Entrez ID   ──┐
GenBank ID  ──┼──> NCBIAdapter ──> NCBI E-utilities API
RefSeq ID   ──┘

Ensembl ID  ──> EnsemblAdapter (coming soon)
UniProt ID  ──> UniProtAdapter (coming soon)
```

### 3. Processing Pipeline

```
Input: Any Gene ID
    ↓
[ID Type Detection]
    ↓
[Get Appropriate Adapter]
    ↓
[Fetch Gene Info] ──> Gene name, description
    ↓
[Get Sequence IDs] ──> Linked sequence IDs
    ↓
[Fetch Sequences] ──> FASTA sequences
    ↓
[Find Longest Sequence]
    ↓
Output: (gene_name, accession, length, sequence, id_type)
```

### 4. Type-Aware Caching

Cache keys include ID type to prevent collisions:

```python
# Old system (collision risk):
cache["12345"] = data

# New system (type-safe):
cache["entrez:12345"] = data
cache["genbank:12345"] = different_data  # Different entry!
```

## Output Format

The script outputs a CSV with these columns:

| Column | Description |
|--------|-------------|
| `miRTarBase ID` | Interaction identifier |
| `miRNA` | miRNA identifier |
| `Gene Symbol` | Gene symbol |
| `Gene ID` | **Your original ID (any type!)** |
| `ID Type` | **Detected ID type** (entrez, genbank, refseq, etc.) |
| `Gene Name` | Gene name from database |
| `Sequence Accession` | Sequence accession number |
| `miRNA Sequence Length` | Length of miRNA sequence |
| `Target Sequence Length` | Length of target sequence |
| `miRNA Sequence` | miRNA nucleotide sequence |
| `Target Sequence` | Target nucleotide sequence |
| `Reference` | PubMed ID reference |

### Example Output

```csv
miRTarBase ID,miRNA,Gene Symbol,Gene ID,ID Type,Gene Name,Sequence Accession,miRNA Sequence Length,Target Sequence Length,miRNA Sequence,Target Sequence,Reference
MIRT001,hsa-miR-21,VP1,12345,entrez,VP1,NC_001234.1,22,7500,TAGCTTATCAGACTGATGTTGA,ATGGATCCG...,28945678
MIRT002,hsa-miR-155,ORF1,NC_045512.2,refseq,ORF1ab,NC_045512.2,23,29903,TTAAAGATCTACAGCTTTC...,ATTAAAGGTT...,32123456
MIRT003,hsa-miR-29,ENV,AB123456.1,genbank,envelope,AB123456.1,22,8500,TAGCTTAACAGACTAATGC,ATGCGATAG...,29876543
```

## ID Type Statistics

After processing, the script displays statistics about ID types found:

```
ID Type Statistics:
  entrez: 45
  refseq: 32
  genbank: 18
  unknown: 5
```

## Architecture

### Class Hierarchy

```
DatabaseAdapter (ABC)
    │
    ├─ NCBIAdapter
    │   ├─ Supports: Entrez, GenBank, RefSeq
    │   └─ API: NCBI E-utilities
    │
    ├─ EnsemblAdapter (future)
    │   ├─ Supports: Ensembl Gene IDs
    │   └─ API: Ensembl REST API
    │
    └─ UniProtAdapter (future)
        ├─ Supports: UniProt IDs
        └─ API: UniProt REST API
```

### ID Type Patterns

```python
class IDType(Enum):
    ENTREZ = "entrez"      # Pure numeric: 12345
    GENBANK = "genbank"    # AB123456, AB_123456.1
    REFSEQ = "refseq"      # NC_001234.1, NM_001234.5
    UNIPROT = "uniprot"    # P12345, Q9Y6K9
    ENSEMBL = "ensembl"    # ENSG00000139618
    EMBL = "embl"          # AJ123456
    UNKNOWN = "unknown"    # Could not detect
```

## Performance

### NCBI-Based IDs (Entrez, GenBank, RefSeq)

| Configuration | Rate Limit | Estimated Time (100 genes) |
|--------------|------------|---------------------------|
| No API Key | 3 req/sec | ~30-60 minutes |
| With API Key | 10 req/sec | ~15-30 minutes |

**Tips for Better Performance:**
1. Get an NCBI API key (free): https://www.ncbi.nlm.nih.gov/account/
2. Use RefSeq or GenBank IDs directly when possible (no linking required)
3. Adjust `number_of_processes` in config

## Column Auto-Detection

The script looks for columns matching these patterns (case-insensitive):

- `.*gene.*id.*` - e.g., "Gene ID", "Target Gene ID"
- `.*entrez.*` - e.g., "Entrez ID", "Entrez Gene"
- `.*genbank.*` - e.g., "GenBank Accession"
- `.*refseq.*` - e.g., "RefSeq ID"
- `.*accession.*` - e.g., "Accession Number"
- `.*target.*id.*` - e.g., "Target ID"

**First match wins!** To be explicit, set `GENE_ID_COLUMN` manually.

## Troubleshooting

### 1. "Could not auto-detect gene ID column"

**Solution:** Specify the column explicitly:
```python
GENE_ID_COLUMN = 'YourColumnName'
```

Check available columns in the log output.

### 2. "Unknown ID type for ID: XYZ"

**Solution:** The ID format isn't recognized. Check if:
- The ID is valid
- The ID type is supported (see table above)
- File an issue if it's a valid ID type we should support

### 3. "No adapter available for ID"

**Solution:** The ID type is detected but not yet implemented. Currently supported:
- Entrez IDs
- GenBank accessions
- RefSeq accessions

Coming soon: Ensembl, UniProt, EMBL

### 4. Rate limit errors

**Solution:**
- Get an NCBI API key
- Reduce `number_of_processes` in config
- Add delays between requests

### 5. Mixed ID types not working

**Good news:** This should work automatically! Each ID is processed with the correct adapter. Check the log to see which type was detected for each ID.

## Adding Support for New ID Types

Want to add support for a new database? Here's how:

### 1. Add ID Pattern

```python
class IDType(Enum):
    # ... existing types ...
    MYDATABASE = "mydatabase"

class IDPattern:
    PATTERNS = {
        # ... existing patterns ...
        IDType.MYDATABASE: r'^MYDB_\d+$',  # Your regex
    }
```

### 2. Create Adapter

```python
class MyDatabaseAdapter(DatabaseAdapter):
    async def get_gene_info(self, gene_id, session):
        # Your implementation
        pass

    async def get_sequence_ids(self, gene_id, session):
        # Your implementation
        pass

    async def get_sequence(self, seq_id, session):
        # Your implementation
        pass

    def get_rate_limit(self):
        return 0.1  # Your rate limit
```

### 3. Register Adapter

```python
def get_adapter_for_id(id_value, api_key=None, email=None):
    id_type = IDPattern.detect_id_type(id_value)

    if id_type == IDType.MYDATABASE:
        return MyDatabaseAdapter(api_key=api_key, email=email)
    # ... existing mappings ...
```

## FAQ

**Q: Can I use this with human genes?**
A: Yes! It works with any organism as long as the IDs are in NCBI databases.

**Q: Can I mix Entrez IDs and GenBank IDs in the same dataset?**
A: Absolutely! The script detects each ID type automatically.

**Q: What if my ID doesn't match any pattern?**
A: It will be marked as "unknown" type. Check the logs for details.

**Q: Can I use this for protein sequences?**
A: Currently optimized for nucleotide sequences. Protein support coming soon!

**Q: Do I need different API keys for different ID types?**
A: Currently, only NCBI API key is used (for Entrez, GenBank, RefSeq). Other databases will have their own auth when implemented.

## API Endpoints Used

### NCBI (Entrez, GenBank, RefSeq)

1. **ESummary** - Get gene/sequence information
   ```
   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi
   ```

2. **ELink** - Find linked sequences (Entrez IDs only)
   ```
   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi
   ```

3. **EFetch** - Retrieve sequences
   ```
   https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
   ```

## Migration from Previous Version

If you're using the old `viral_entrez_fetcher.py`:

### Old Code:
```python
# Hardcoded for Entrez IDs only
entrez_id = int(row['Target Gene (Entrez ID)'])
gene_name, accession, length, sequence = await processViralGene(entrez_id, session)
```

### New Code:
```python
# Works with ANY ID type!
gene_id = row[GENE_ID_COLUMN]  # Can be any type
gene_name, accession, length, sequence, id_type = await processGeneID(gene_id, session)
```

**Your existing datasets will work without changes!** The script maintains backward compatibility.

## References

- [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [GenBank](https://www.ncbi.nlm.nih.gov/genbank/)
- [RefSeq](https://www.ncbi.nlm.nih.gov/refseq/)
- [UniProt](https://www.uniprot.org/)
- [Ensembl](https://www.ensembl.org/)

## Contributing

Found a bug or want to add support for a new ID type?

1. Check existing issues
2. Add your ID type pattern
3. Implement the adapter
4. Submit a pull request!

## License

Same as original code.

---

**Made with ❤️ for researchers working with ANY type of genomic identifiers!**

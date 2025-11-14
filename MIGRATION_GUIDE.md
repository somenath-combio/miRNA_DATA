# Migration Guide: Human → Viral Version

This guide shows key code changes when migrating from human Ensembl-based fetcher to viral NCBI-based fetcher.

## 1. API Initialization

### Human Version (Ensembl)
```python
# No special initialization needed
# Ensembl REST API is open and permissive
```

### Viral Version (NCBI)
```python
# REQUIRED: Email and optional API key
ENTREZ_EMAIL = "your.email@example.com"
ENTREZ_API_KEY = "your_api_key"  # Optional but recommended

# NCBI base URL
NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
```

## 2. Gene ID Lookup

### Human Version
```python
async def getGeneID(entrez_id: int, session: RetryClient, species: str = 'human') -> list:
    base_url = f"https://rest.ensembl.org/xrefs/symbol/{species}/{entrez_id}"
    headers = {"Content-Type": "application/json"}
    data = await fetchWithRetry(url=base_url, session=session, headers=headers)
    gene_ids = [gene['id'] for gene in data if gene['type'] == 'gene'] if data else []
    return gene_ids
```

### Viral Version
```python
async def getGeneInfo(entrez_id: int, session: RetryClient) -> Optional[Dict]:
    url = f"{NCBI_EUTILS_BASE}/esummary.fcgi"
    params = {
        "db": "gene",
        "id": entrez_id,
        "retmode": "xml",
        "api_key": ENTREZ_API_KEY  # if available
    }
    data = await fetchWithRetry(url=url, session=session, params=params)

    # Parse XML instead of JSON
    root = ET.fromstring(data)
    gene_name = root.findtext(".//DocumentSummary/Name")
    return {"gene_name": gene_name, "entrez_id": entrez_id}
```

**Key Changes:**
- JSON → XML parsing
- Direct gene info retrieval (no Ensembl ID conversion needed)
- Added API key support

## 3. Sequence ID Discovery

### Human Version
```python
async def getTranscriptID(gene_id: str, session: RetryClient) -> list:
    base_url = f"https://rest.ensembl.org/lookup/id/{gene_id}?expand=1"
    headers = {"Content-Type": "application/json"}
    data = await fetchWithRetry(url=base_url, session=session, headers=headers)
    transcript_ids = [transcript['id'] for transcript in data.get('Transcript', [])]
    return transcript_ids
```

### Viral Version
```python
async def getNucleotideIDs(entrez_id: int, session: RetryClient) -> List[str]:
    url = f"{NCBI_EUTILS_BASE}/elink.fcgi"
    params = {
        "dbfrom": "gene",
        "db": "nucleotide",
        "id": entrez_id,
        "retmode": "xml",
        "api_key": ENTREZ_API_KEY
    }
    data = await fetchWithRetry(url=url, session=session, params=params)

    # Parse XML to get linked nucleotide IDs
    root = ET.fromstring(data)
    nucl_ids = [link.text for link in root.findall(".//Link/Id")]
    return nucl_ids
```

**Key Changes:**
- Gene → Nucleotide linking (instead of Gene → Transcript)
- XML parsing with XPath
- Direct database linking via ELink

## 4. Sequence Fetching

### Human Version
```python
async def getSequence(transcript_id: str, session: RetryClient) -> str:
    base_url = f"https://rest.ensembl.org/sequence/id/{transcript_id}?type=cdna"
    headers = {"Content-Type": "text/plain"}
    data = await fetchWithRetry(url=base_url, session=session, headers=headers)
    return data  # Returns sequence directly
```

### Viral Version
```python
async def getSequence(nucl_id: str, session: RetryClient) -> Optional[Tuple[str, int, str]]:
    url = f"{NCBI_EUTILS_BASE}/efetch.fcgi"
    params = {
        "db": "nucleotide",
        "id": nucl_id,
        "rettype": "fasta",
        "retmode": "text",
        "api_key": ENTREZ_API_KEY
    }
    data = await fetchWithRetry(url=url, session=session, params=params)

    # Parse FASTA format
    lines = data.strip().split('\n')
    header = lines[0]
    sequence = ''.join(lines[1:])
    return sequence, len(sequence), nucl_id
```

**Key Changes:**
- FASTA format parsing (header + sequence)
- Returns tuple with more metadata
- Nucleotide database instead of cDNA

## 5. Rate Limiting

### Human Version
```python
async with RetryClient(retry_options=retry_options) as session:
    semaphore = asyncio.Semaphore(100)  # High concurrency
    # No sleep between requests
```

### Viral Version
```python
async with RetryClient(retry_options=retry_options) as session:
    semaphore = asyncio.Semaphore(3 if ENTREZ_API_KEY else 2)  # Low concurrency

    # Required sleep between requests
    for nucl_id in nucl_ids:
        result = await getSequence(nucl_id=nucl_id, session=session)
        await asyncio.sleep(0.15 if ENTREZ_API_KEY else 0.35)  # NCBI rate limit
```

**Key Changes:**
- Reduced concurrency (100 → 2-3)
- Added sleep between requests
- Different rates for API key vs no key

## 6. Fallback Strategy

### Human Version
```python
# No fallback - Ensembl data is well-linked
for gene_id in ensembl_gene_idx:
    transcript_idx = await getTranscriptID(gene_id=gene_id, session=session)
    for transcript_id in transcript_idx:
        seq = await getSequence(transcript_id=transcript_id, session=session)
```

### Viral Version
```python
# Primary: Use linked nucleotide sequences
nucl_ids = await getNucleotideIDs(entrez_id=entrez_id, session=session)
if nucl_ids:
    for nucl_id in nucl_ids:
        result = await getSequence(nucl_id=nucl_id, session=session)

# Fallback: Direct gene fetch if no links found
if max_seq is None:
    result = await getSequenceByGeneID(entrez_id=entrez_id, session=session)
```

**Key Changes:**
- Added fallback for missing links
- Viral genes may not have proper nucleotide linking
- Direct gene FASTA fetch as backup

## 7. Process Configuration

### Human Version
```python
number_of_processes = cpu_count() * 4  # Aggressive parallelization
chunk_size = max(1, len(mirBase_df) // (number_of_processes // 2))
```

### Viral Version
```python
number_of_processes = min(cpu_count(), 4)  # Conservative due to API limits
chunk_size = max(1, len(mirBase_df) // (number_of_processes * 2))
```

**Key Changes:**
- Reduced process count (respect NCBI limits)
- Smaller chunks for better distribution
- Conservative approach to avoid 429 errors

## 8. Output Schema

### Human Version
```python
return {
    "miRTarBase ID": miRNATarBaseID,
    "miRNA": miRNA,
    "Gene Symbol": targetGeneSymbol,
    "Entrez ID": entrez_id,
    "Ensembl Gene ID": max_seq_gene_id,           # Ensembl-specific
    "Ensembl Transcript ID": max_seq_transcript_id,  # Ensembl-specific
    "miRNA Sequence Length": miRNA_seq_len,
    "mRNA Sequence Length": max_seq_len,
    "miRNA Sequence": miRNA_seq,
    "mRNA Sequence": max_seq,                      # Human mRNA
    "Reference": reference
}
```

### Viral Version
```python
return {
    "miRTarBase ID": miRNATarBaseID,
    "miRNA": miRNA,
    "Gene Symbol": targetGeneSymbol,
    "Entrez ID": entrez_id,
    "Gene Name": gene_name,                        # NCBI gene name
    "Nucleotide Accession": seq_accession,         # GenBank accession
    "miRNA Sequence Length": miRNA_seq_len,
    "Viral Sequence Length": seq_len,
    "miRNA Sequence": miRNA_seq,
    "Viral Sequence": seq,                         # Viral genome/gene
    "Reference": reference
}
```

**Key Changes:**
- Ensembl IDs → Gene Name + Nucleotide Accession
- mRNA → Viral Sequence (terminology)
- GenBank accession numbers instead of Ensembl IDs

## Summary Table

| Feature | Human (Ensembl) | Viral (NCBI) |
|---------|----------------|--------------|
| **API** | Ensembl REST | NCBI E-utilities |
| **Auth** | None | Email required |
| **Format** | JSON | XML + FASTA |
| **Rate Limit** | ~15/sec | 3-10/sec |
| **Concurrency** | 100 | 2-3 |
| **Processes** | CPU × 4 | min(CPU, 4) |
| **ID Type** | Ensembl Gene/Transcript | Entrez Gene + GenBank |
| **Sequence** | cDNA transcripts | Nucleotide sequences |
| **Fallback** | None needed | Direct gene fetch |
| **Sleep** | No | Yes (0.15-0.35s) |

## Quick Migration Checklist

- [ ] Install same dependencies (`requirements.txt`)
- [ ] Set `ENTREZ_EMAIL` in code
- [ ] (Optional) Get and set `ENTREZ_API_KEY`
- [ ] Update input CSV path to viral dataset
- [ ] Verify Entrez IDs are for viral genes
- [ ] Reduce `number_of_processes` if getting 429 errors
- [ ] Update output column names in downstream analysis
- [ ] Expect slower runtime (API limits)
- [ ] Check logs in `viral_fetcher.log`

## Testing

### Test with a small dataset first:

```python
# In __main__ section, add:
mirBase_df = mirBase_df.head(10)  # Test with 10 rows first
```

### Verify a single Entrez ID manually:

Visit: https://www.ncbi.nlm.nih.gov/gene/[ENTREZ_ID]

Check:
- Is it a viral gene?
- Are there linked nucleotide sequences?
- What's the organism?

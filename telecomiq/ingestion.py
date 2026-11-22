"""Optional pinned HF dataset-file importer; no remote code execution or automatic publication."""
import re,json
from pathlib import Path,PurePosixPath
from .engine import require

def stage_huggingface_file(engine,identity,repo_id,filename,revision,text_column='text',license_note='',limit=30):
 require(identity,'knowledge.review')
 if not re.fullmatch(r'[0-9a-f]{40}',revision):raise ValueError('A reviewed full 40-character commit SHA is required')
 if not license_note.strip():raise ValueError('Record reviewed licence/provenance before import')
 if '..' in PurePosixPath(filename).parts or PurePosixPath(filename).is_absolute():raise ValueError('Invalid repository path')
 from huggingface_hub import hf_hub_download
 path=Path(hf_hub_download(repo_id=repo_id,repo_type='dataset',filename=filename,revision=revision))
 if path.stat().st_size>10_000_000:raise ValueError('Dataset file exceeds 10 MB; curate a smaller file')
 results=[]
 if path.suffix=='.jsonl':
  lines=path.read_text().splitlines()[:min(100,int(limit))]
  for i,line in enumerate(lines):
   row=json.loads(line);body=str(row.get(text_column,''))
   if body.strip():results.append(engine.stage_upload(identity,f'hf-{i}.txt',body.encode(),{},f'https://huggingface.co/datasets/{repo_id}/blob/{revision}/{filename}',license_note))
 else:results.append(engine.stage_upload(identity,path.name,path.read_bytes(),{},f'https://huggingface.co/datasets/{repo_id}/blob/{revision}/{filename}',license_note))
 return results

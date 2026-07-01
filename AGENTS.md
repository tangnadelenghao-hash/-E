## PDF Reading Workflow

When a task requires reading a PDF, use the known-good workflow below.

1. Prefer the bundled Codex Python runtime after calling `load_workspace_dependencies`
   when available.
2. Do not use Bash-style here-doc syntax such as `python - <<'PY'` in PowerShell.
   It fails because PowerShell treats `<` as a redirection operator.
3. For directories containing multiple PDF files, first enumerate `*.pdf` files and
   select the target by exact filename or a checked index. Do not assume the first
   PDF in the directory is the requested file.
4. In PowerShell, set UTF-8 output before printing extracted Chinese text:
   `$env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8`
5. Feed Python code through a PowerShell here-string piped to Python:

```powershell
$env:PYTHONIOENCODING='utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
@'
import pathlib
import sys
import pdfplumber

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

base = pathlib.Path(r'C:\path\to\pdf\directory')
pdfs = sorted(base.glob('*.pdf'))
for index, path in enumerate(pdfs):
    print(index, path.name)

target = next(path for path in pdfs if path.name == 'target.pdf')
with pdfplumber.open(target) as pdf:
    print('pages', len(pdf.pages))
    for page_number, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ''
        print(f'---PAGE {page_number}---')
        print(text[:5000])
'@ | & 'C:\Users\HUAWEI\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -
```

6. If layout fidelity matters, render pages to images and inspect them. If only task
   requirements or plain text are needed, `pdfplumber` text extraction is acceptable.

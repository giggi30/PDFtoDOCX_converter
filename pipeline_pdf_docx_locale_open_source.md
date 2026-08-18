d# Pipeline locale open-source PDF → DOCX ad alta fedeltà

## Obiettivo

Costruire in locale e senza dipendenze SaaS un convertitore PDF → DOCX modificabile ispirato al modello operativo di CloudConvert: un **job** è una sequenza di **task** indipendenti, con input e output espliciti, stato persistente, osservabilità e possibilità di comporre più operazioni.

CloudConvert organizza l'elaborazione in job composti da task; separa import, conversione ed export, consente workflow con rami multipli e supporta esecuzione asincrona o sincrona. Il suo servizio PDF→Office dichiara di usare la tecnologia commerciale Apryse per la conversione di alta qualità. Qui si replica **l'architettura della pipeline**, non l'engine proprietario.

Vincolo principale: la conversione PDF → DOCX non può essere perfetta in generale. Il PDF è una descrizione grafica a coordinate, mentre DOCX è un modello semantico e reflowabile. Il sistema deve quindi ricostruire una struttura modificabile con euristiche, OCR e validazione.

---

## Principi progettuali

- **Local-first**: file, cache, database e worker restano sulla macchina o nella rete privata.
- **Gratuito e open source**: nessun SDK o API a pagamento.
- **Pipeline dichiarativa**: il job è un DAG/JSON di task, non una singola funzione monolitica.
- **Riproducibilità**: fissare versioni dei tool e salvare configurazione, input hash, log e artefatti intermedi.
- **Selezione condizionale**: classificare il PDF prima della conversione e scegliere la strategia appropriata.
- **Qualità misurabile**: renderizzare il DOCX di nuovo in PDF e confrontarlo con l'originale.
- **Fail soft**: se un elemento non è ricostruibile semanticamente, conservarne la resa visiva come immagine invece di perderlo.

---

## Stack open source consigliato

| Responsabilità | Scelta primaria | Alternative | Note |
|---|---|---|---|
| Ispezione e rendering PDF | PyMuPDF (`pymupdf`) | Poppler (`pdftoppm`), MuPDF CLI | Estrae testo, blocchi, font, immagini e disegni vettoriali |
| PDF testuale → DOCX | `pdf2docx` | Implementazione custom PyMuPDF + `python-docx` | Buon baseline per layout, tabelle e immagini |
| Generazione/modifica DOCX | `python-docx` | `docxtpl` per template | `python-docx` non espone tutte le feature OOXML: usare XML quando necessario |
| OCR PDF scannerizzato | OCRmyPDF + Tesseract | PaddleOCR, EasyOCR | OCRmyPDF aggiunge un text layer al PDF e conserva l'originale |
| OCR di layout complesso | PaddleOCR / PP-Structure | docTR | Utile come fallback quando Tesseract segmenta male tabelle o colonne |
| Deskew/denoise immagini | OpenCV | ImageMagick | Solo quando serve, per non degradare documenti nativi |
| Conversione DOCX → PDF per QA | LibreOffice headless | unoconv | Usare una versione fissata in container |
| Diff visivo | ImageMagick (`compare`) + SSIM OpenCV | Pixelmatch | Confrontare page-by-page a DPI costante |
| Persistenza job | SQLite | PostgreSQL | SQLite basta per uso personale e worker locale |
| Coda task | `asyncio` + process pool | Celery + Redis, RQ | Celery serve solo con più worker/macchine |
| API locale | FastAPI | CLI Typer | API utile per GUI React o automazione |
| Isolamento runtime | Docker/Compose | `uv` + virtualenv | Container consigliato per riproducibilità |

### Licenze: attenzione

`pdf2docx` è pubblicato con licenza AGPL-3.0: se distribuisci il convertitore come servizio o prodotto, verifica attentamente gli obblighi di licenza e valuta un'implementazione custom basata su PyMuPDF e `python-docx`. Tesseract, OCRmyPDF, LibreOffice, OpenCV, FastAPI e SQLite sono invece adatti a una pipeline locale open-source, ma le rispettive licenze vanno comunque inventariate nel progetto.

---

## Modello CloudConvert da copiare

### Entità principali

```text
Job
 ├── id, tag, status, created_at, started_at, ended_at
 ├── source manifest (file, hash SHA-256, metadati)
 ├── settings snapshot (versioni tool + parametri)
 ├── tasks[]
 └── artifacts[]

Task
 ├── id, operation, depends_on[]
 ├── input artifact references
 ├── status: waiting | queued | processing | finished | warning | error | skipped
 ├── attempts, timing, stderr/stdout
 ├── options JSON
 └── output artifact references

Artifact
 ├── id, path, media_type, sha256, size
 ├── producer_task_id
 └── metadata JSON
```

### Stati del job

```text
created → queued → processing → finished
                    ├────────→ finished_with_warnings
                    ├────────→ failed
                    └────────→ cancelled
```

Un task viene eseguito solo quando tutte le dipendenze sono `finished` o `warning`. Un errore bloccante propaga `skipped` ai task dipendenti; un errore non bloccante crea un warning e consente un fallback.

### Operazioni locali

| Operazione | Input | Output | Funzione |
|---|---|---|---|
| `import/local` | path locale | PDF copiato nel workspace | Congela input e calcola hash |
| `inspect/pdf` | PDF | manifesto JSON | Determina pagine, testo, font, immagini, rotazioni, encryption |
| `classify/pdf` | manifesto | decision JSON | Sceglie native/OCR/hybrid e profilo layout |
| `preprocess/pdf` | PDF + decisione | PDF normalizzato | Decrypt autorizzato, rotate, deskew, cleanup opzionale |
| `ocr/pdf` | PDF raster/scannerizzato | searchable PDF + OCR JSON | Aggiunge text layer e coordinate |
| `extract/layout` | PDF | layout JSON + asset | Blocchi, linee, immagini, path, tabelle candidate |
| `convert/docx` | layout JSON/PDF | DOCX | Ricostruisce documento editabile |
| `render/docx` | DOCX | PDF di verifica + PNG pagine | LibreOffice headless |
| `validate/visual` | PDF originale + PDF renderizzato | quality report JSON | Metriche pagine, SSIM, differenze, anomalie |
| `validate/semantic` | PDF/OCR text + DOCX text | semantic report JSON | Confronta testo, numeri, tabelle e pagine |
| `fallback/rasterize` | regioni problematiche | immagini PNG + DOCX aggiornato | Preserva visivamente elementi non ricostruibili |
| `export/local` | DOCX + report | cartella destinazione | Copia atomica e produce manifest finale |

---

## Pipeline base

```text
import/local
  → inspect/pdf
  → classify/pdf
  → preprocess/pdf (se necessario)
  ├→ ocr/pdf (solo scan o PDF ibrido degradato)
  └→ extract/layout
       → convert/docx
       → render/docx
       ├→ validate/visual
       └→ validate/semantic
            → fallback/rasterize (solo regioni sotto soglia)
            → render/docx (secondo passaggio)
            → validate/visual (secondo passaggio)
                 → export/local
```

La parte importante è il **ciclo di quality assurance**: convertire non basta. Il DOCX va renderizzato di nuovo in PDF e confrontato con l'input; soltanto gli elementi problematici vengono degradati a immagine, mantenendo editabile tutto il resto.

---

## Step 1 — Import e workspace immutabile

Per ogni job crea una directory isolata:

```text
workspaces/
  <job-id>/
    input/original.pdf
    manifest/input.json
    intermediate/
    artifacts/
    logs/
    reports/
```

Durante `import/local`:

1. Copia il file invece di elaborare il path originale.
2. Calcola SHA-256, MIME type, dimensione e timestamp.
3. Valida il magic header `%PDF-` e limita dimensione/pagine configurabili.
4. Non processare PDF cifrati senza una password fornita esplicitamente dall'utente.
5. Salva una configurazione completa del job prima di avviare i worker.

Esempio di manifest:

```json
{
  "job_id": "01J...",
  "source": {"path": "input/original.pdf", "sha256": "...", "size": 348921},
  "runtime": {
    "pymupdf": "pinned-version",
    "pdf2docx": "pinned-version",
    "tesseract": "pinned-version",
    "libreoffice": "pinned-version"
  },
  "profile": "balanced",
  "created_at": "2026-08-16T...Z"
}
```

---

## Step 2 — Ispezione e classificazione

Non inviare tutti i PDF al medesimo convertitore. Calcola feature per pagina e per documento.

### Feature da estrarre con PyMuPDF

- Numero di caratteri e di parole estraibili.
- Copertura del testo: area dei blocchi testuali / area pagina.
- Numero, area e DPI stimato delle immagini.
- Presenza di font embedded e font non standard.
- Blocchi con rotazione o matrici trasformate.
- Path vettoriali, linee, rettangoli e densità di disegni.
- Numero di colonne stimato tramite clustering delle coordinate X.
- Presenza di annotazioni, moduli AcroForm, firme e PDF cifrati.
- Pagine miste: testo nativo più scansione o immagine di sfondo.

### Regole iniziali di classificazione

| Classe | Indicatore pratico | Azione |
|---|---|---|
| `native_text` | testo estraibile abbondante e immagini limitate | Conversione layout-aware diretta |
| `scanned` | testo quasi assente e una grande immagine per pagina | OCRmyPDF prima della conversione |
| `hybrid` | testo estraibile ma bassa copertura o immagini dominanti | OCR selettivo / analisi per regione |
| `table_heavy` | molte linee ortogonali o allineamenti ripetuti | Abilita entrambi i detector tabella |
| `form_like` | campi, box, label allineate | Posizionamento assoluto o tabella invisibile |
| `complex_graphics` | molti path/forme, testo su grafici | Conserva grafici come immagini raster ad alta risoluzione |
| `unsafe` | cifratura, corruzione, file enorme | Rifiuta o richiedi intervento utente |

Queste euristiche sono un baseline. Salva le feature e gli esiti QA per costruire in seguito un classificatore ML leggero o un sistema di regole calibrato sui tuoi documenti reali.

---

## Step 3 — Preprocessing controllato

Il preprocessing deve essere **condizionale**. Applicarlo sempre rischia di alterare font, colori e precisione del layout.

### Per PDF nativi

- Mantieni il PDF originale come fonte di verità.
- Correggi soltanto rotazioni di pagina esplicite.
- Estrai immagini originali quando possibile, senza rasterizzare l'intera pagina.
- Evita OCR globale: può introdurre testo duplicato o coordinate errate.

### Per scansioni

Esegui OCRmyPDF con lingua coerente con il documento, preservando il file iniziale:

```bash
ocrmypdf \
  --skip-text \
  --rotate-pages \
  --deskew \
  --clean \
  --optimize 1 \
  -l ita+eng \
  input/original.pdf intermediate/ocr.pdf
```

Indicazioni:

- `--skip-text` evita di ri-OCRizzare pagine che possiedono già text layer.
- `--deskew` e `--clean` sono utili per scansioni, ma testa l'impatto su timbri, codici a barre e testo molto piccolo.
- Per documenti con numeri, codici e tabelle dense, conserva l'output OCR e le confidence quando disponibili: serviranno alla validazione.
- Se il documento contiene dati in italiano, usa `ita`; aggiungi `eng` per codici, intestazioni o documenti misti.

---

## Step 4 — Estrazione del layout intermedio

Non passare direttamente PDF → DOCX senza un artefatto intermedio. Crea un `layout.json` stabile, ispezionabile e testabile.

### Schema minimo per pagina

```json
{
  "page": 1,
  "width_pt": 595.276,
  "height_pt": 841.89,
  "rotation": 0,
  "blocks": [
    {
      "id": "b-001",
      "type": "text|image|table|vector|unknown",
      "bbox": [x0, y0, x1, y1],
      "z_index": 3,
      "confidence": 0.94,
      "payload": {}
    }
  ],
  "reading_order": ["b-001", "b-002"]
}
```

### Testo

Conserva, per ogni span/riga/blocco:

- Bounding box in punti PDF.
- Testo Unicode normalizzato e testo originale.
- Font name, dimensione, bold, italic, colore, underline, strike-through.
- Baseline, direzione e spaziatura.
- Indici nel reading order.

### Immagini

Salva l'immagine originale in `artifacts/images/` e registra:

- Bbox, DPI stimato, alpha channel e crop.
- Relazione con il testo: inline, floating, sfondo o sovrapposta.
- Hash del contenuto estratto per deduplicazione.

### Vettori e forme

- Raccogli linee e rettangoli con coordinate, spessore e colore.
- Interpreta prima le griglie tabellari; se non sono tabella, valuta se convertirle in forme OOXML o rasterizzarle.
- Per grafici complessi, rasterizza la sola regione a 200–300 DPI e inseriscila come immagine, mantenendo la qualità visiva.

---

## Step 5 — Ricostruzione semantica

### Ordine di lettura

Il PDF non garantisce l'ordine logico dei frammenti. Ricostruiscilo con un algoritmo per pagina:

1. Dividi gli elementi in zone/colonne mediante gap orizzontali e overlap degli intervalli X.
2. In ogni zona, ordina righe e blocchi dall'alto al basso usando baseline e bbox.
3. Raggruppa le righe in paragrafi con distanza verticale, indentazione, allineamento e stile coerente.
4. Riconosci header/footer ripetuti confrontando posizione e contenuto su più pagine.
5. Collega testo a immagini e didascalie con prossimità spaziale.

### Paragrafi

Unisci due righe se:

- hanno font e stile compatibili;
- il loro overlap orizzontale è significativo;
- il gap verticale è vicino all'interlinea del blocco;
- la riga precedente non termina con un segnale forte di fine paragrafo;
- la nuova riga non ricomincia con indentazione, bullet o numerazione incompatibile.

In DOCX conserva stile run-level (font, peso, colore, underline) e paragraph-level (alignment, indentation, spacing). Non usare un textbox per ogni riga: aumenta la fedeltà apparente ma riduce drasticamente l'editabilità.

### Colonne

Per massimizzare l'editabilità:

- Se la pagina ha 1–2 colonne pulite, usa sezioni/colonne DOCX.
- Se ha layout a blocchi irregolari (newsletter, brochure, moduli), preferisci tabelle senza bordi o text box ancorate.
- Se la ricostruzione genera sovrapposizioni o reflow grave, crea una pagina visuale con immagine di sfondo e overlay editabile soltanto per i campi prioritari, dichiarando il compromesso nel report.

---

## Step 6 — Rilevamento e costruzione tabelle

Usa due detector, come pattern generale di converter professionali.

### Tabelle lattice (con bordi)

1. Estrai segmenti verticali e orizzontali dai drawing/path del PDF.
2. Normalizza linee quasi coincidenti con una tolleranza in punti.
3. Collega segmenti e individua rettangoli/celle.
4. Determina righe e colonne dai confini unici.
5. Assegna text spans a una cella usando overlap dell'area; risolvi span celle e celle fuse.
6. Riproduci bordi, shading, allineamento verticale e merge in DOCX.

### Tabelle stream (senza bordi)

1. Clusterizza gli x-start e x-end delle parole/righe.
2. Cerca colonne persistenti in un intervallo verticale.
3. Identifica le righe tramite baseline ravvicinate.
4. Verifica coerenza: numero colonne, gap, allineamento numerico e righe header.
5. Genera tabella DOCX solo se la confidence supera una soglia; altrimenti mantieni paragrafi tabulati o usa un fallback visivo.

### Validazione delle tabelle

- Confronta numero di celle, stringhe, numeri, date e importi tra layout JSON e DOCX.
- Confronta la geometria renderizzata della tabella con la regione PDF originale.
- Non inventare confini assenti: un falso positivo tabella è spesso più dannoso di testo correttamente preservato ma non tabellare.

---

## Step 7 — Generazione DOCX

### Strategia a livelli

1. **Struttura semantica**: heading, paragrafi, liste, tabelle e immagini inline.
2. **Stili**: font, dimensioni, colori, spacing, bordi e shading.
3. **Geometria**: margini pagina, colonne, larghezze tabelle e posizionamento floating.
4. **Fallback visuale**: immagine soltanto per elementi che non superano i controlli di qualità.

### Mapping delle coordinate

PDF e DOCX usano entrambi unità riconducibili ai punti tipografici, ma Word ricalcola il layout usando font e metriche disponibili. Per ridurre drift:

- Imposta page size e margini DOCX uguali al PDF.
- Usa font installati localmente e definisci una mappa di fallback controllata.
- Evita di convertire tutte le posizioni in `absolute`; usale per elementi flottanti, moduli e layout irregolari.
- Imposta dimensioni e larghezze in punti/twips, evitando percentuali.
- Mantieni uno stile DOCX esplicito invece di affidarti ai default di Word.

### Quando usare XML OOXML direttamente

`python-docx` è adeguato per paragrafi, tabelle e immagini inline. Per fedeltà avanzata può essere necessario intervenire nell'XML del package DOCX per:

- immagini floating e wrapping;
- shading/bordi non esposti dall'API;
- ancoraggi e offset;
- impostazioni sezione e colonne;
- proprietà delle celle e merge complessi.

Isola questo codice in un modulo `ooxml_adapter.py`; evita che dettagli OOXML contaminino il parser del PDF.

---

## Step 8 — QA visuale e semantico

### QA visuale

1. Converti il DOCX in PDF con LibreOffice headless.
2. Rasterizza sia l'originale sia il PDF renderizzato alla stessa risoluzione, ad esempio 150 DPI per test rapidi e 300 DPI per artefatti finali.
3. Allinea le pagine; se necessario compensa una piccola traslazione globale.
4. Calcola SSIM e percentuale di pixel differenti per pagina e per regione.
5. Genera un'immagine diff evidenziata e salva le bounding box problematiche.

Una formula possibile per lo score composito è:

```text
quality = 0.45 * visual_ssim
        + 0.25 * text_similarity
        + 0.20 * table_score
        + 0.10 * image_coverage
```

Le soglie vanno calibrate su un set di PDF rappresentativo. Non dichiarare una conversione “perfetta” basandoti solo su SSIM: un testo semanticamente errato può avere una resa visiva simile.

### QA semantico

- Estrai testo dal PDF originale (o dal PDF OCR) e dal DOCX renderizzato/estratto.
- Normalizza spazi, soft hyphen, Unicode, date e separatori numerici prima del confronto.
- Confronta pagine e blocchi, non solo il documento intero.
- Per tabelle, confronta celle e valori normalizzati; per importi e codici usa matching esatto e segnala differenze.
- Segnala font sostituiti, immagini mancanti, pagine aggiunte/rimosse, rotazioni e overflow.

### Politica di fallback

| Esito regione | Azione |
|---|---|
| Alta qualità visiva e semantica | Mantieni elemento editabile |
| Testo corretto, layout degradato | Regola spacing, larghezza, tab stop o posizione |
| Layout corretto, testo degradato | Ricorri all'OCR/regione o conserva testo nascosto verificabile |
| Tabella incerta | Mantieni struttura tabellare solo sopra soglia, altrimenti usa fallback visuale |
| Grafico/forma complessa | Rasterizza esclusivamente la regione e inseriscila in DOCX |
| Pagina gravemente non ricostruibile | Inserisci pagina come immagine ad alta risoluzione e marca il report |

---

## Profili di conversione

Esporre profili semplici evita che l'utente debba conoscere tutte le euristiche.

### `editable`

Priorità: semantica e modificabilità.

- Più aggressivo nella ricostruzione di paragrafi e tabelle.
- Pochi elementi rasterizzati.
- Accetta una fedeltà visuale leggermente inferiore.

### `balanced` (default)

Priorità: buon equilibrio tra layout e editabilità.

- PDF testuali: `pdf2docx` o parser custom.
- Scansioni: OCRmyPDF prima della conversione.
- Fallback per regioni che falliscono QA.

### `visual`

Priorità: resa grafica.

- Usa elementi floating e fallback raster con più frequenza.
- Conserva layout di brochure, moduli e grafici.
- Meno adatto se l'utente vuole riformattare il testo.

### `tables`

Priorità: estrazione tabelle.

- Abilita lattice + stream detection.
- Genera report cella-per-cella.
- Conserva come immagine tabelle che non raggiungono la soglia configurata.

---

## API locale proposta

### Creazione job

```http
POST /v1/jobs
Content-Type: application/json

{
  "input_path": "/absolute/path/documento.pdf",
  "output_dir": "/absolute/path/output",
  "profile": "balanced",
  "options": {
    "ocr_languages": ["ita", "eng"],
    "max_pages": 100,
    "keep_intermediates": true,
    "visual_threshold": 0.92,
    "semantic_threshold": 0.98
  }
}
```

### Risposta

```json
{
  "id": "01J...",
  "status": "queued",
  "tasks": [
    "import/local",
    "inspect/pdf",
    "classify/pdf",
    "convert/docx",
    "validate/visual",
    "export/local"
  ]
}
```

### Stato e risultato

```http
GET /v1/jobs/{job_id}
GET /v1/jobs/{job_id}/artifacts
GET /v1/jobs/{job_id}/report
POST /v1/jobs/{job_id}/cancel
```

Per un uso interattivo, pubblica eventi WebSocket o Server-Sent Events: `task.started`, `task.progress`, `task.warning`, `task.finished`, `job.finished`.

---

## Interfacce Python

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

@dataclass
class Artifact:
    id: str
    path: Path
    media_type: str
    sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskResult:
    status: str
    artifacts: list[Artifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

@dataclass
class TaskContext:
    job_id: str
    workspace: Path
    config: dict[str, Any]
    artifacts: dict[str, Artifact]

class Task(Protocol):
    operation: str

    def run(self, context: TaskContext) -> TaskResult:
        ...

class ConversionEngine(Protocol):
    name: str
    version: str

    def convert(self, pdf: Path, layout: Path, destination: Path, options: dict[str, Any]) -> TaskResult:
        ...
```

Implementazioni iniziali:

```text
engines/
  pdf2docx_engine.py      # baseline rapido, per PDF text-based
  native_layout_engine.py # obiettivo: PyMuPDF + layout.json + python-docx/OOXML
  raster_fallback.py      # conversione per regioni/pagine problematiche
```

L'interfaccia consente di confrontare engine e versioni sullo stesso corpus senza cambiare il resto della pipeline.

---

## Implementazione incrementale

### Milestone 1 — MVP affidabile

- CLI: `convert input.pdf --output out.docx`.
- Workspace, manifest, hash e log.
- `pdf2docx` per PDF testuali.
- OCRmyPDF + Tesseract per PDF scannerizzati.
- Export locale di DOCX e report JSON essenziale.

### Milestone 2 — Job engine

- SQLite con job/task/artifact.
- Worker locale e stati persistenti.
- API FastAPI e progress event.
- Retry espliciti solo per errori transitori e con numero massimo di tentativi.

### Milestone 3 — Quality loop

- LibreOffice headless per render DOCX→PDF.
- Rasterizzazione e visual diff page-by-page.
- Similarità testo e report per pagine/regioni.
- Fallback raster automatico per grafici e regioni sotto soglia.

### Milestone 4 — Parser proprietario

- Layout JSON stabilizzato e testabile.
- Ordine di lettura, paragrafi e due detector tabelle.
- Generazione DOCX tramite `python-docx` + adapter OOXML.
- Benchmark ripetibili tra parser custom e `pdf2docx`.

### Milestone 5 — Hardening

- Container Docker con versioni bloccate.
- Limiti di risorse per subprocess (CPU, RAM, timeout, max page count).
- Sanitizzazione path, sandbox workspace e pulizia automatica.
- Test corpus anonimo con golden files e metriche di regressione.

---

## Struttura repository suggerita

```text
pdf-docx-local/
  app/
    api/
    core/
      jobs.py
      scheduler.py
      artifacts.py
      state_store.py
    tasks/
      import_local.py
      inspect_pdf.py
      classify_pdf.py
      preprocess_pdf.py
      ocr_pdf.py
      extract_layout.py
      convert_docx.py
      render_docx.py
      validate_visual.py
      validate_semantic.py
      fallback_rasterize.py
      export_local.py
    engines/
      pdf2docx_engine.py
      native_layout_engine.py
      ooxml_adapter.py
    services/
      pymupdf_service.py
      ocr_service.py
      libreoffice_service.py
      diff_service.py
  tests/
    fixtures/
    golden/
    test_tasks/
    test_e2e/
  docker/
  docs/
  workspaces/       # gitignored
  pyproject.toml
  compose.yaml
```

---

## Dipendenze iniziali

```toml
[project]
dependencies = [
  "pymupdf",
  "pdf2docx",
  "python-docx",
  "ocrmypdf",
  "pytesseract",
  "opencv-python-headless",
  "Pillow",
  "fastapi",
  "uvicorn[standard]",
  "sqlalchemy",
  "pydantic",
  "typer",
  "structlog"
]
```

Dipendenze di sistema da installare separatamente:

```text
Tesseract + language packs (ita, eng)
Ghostscript
qpdf
LibreOffice
Poppler oppure MuPDF tools
ImageMagick (opzionale per diff)
```

Per OCRmyPDF, usa una distribuzione supportata e verifica l'installazione delle dipendenze native nel container Linux scelto.

---

## Comandi di sviluppo utili

```bash
# PDF nativo → DOCX con baseline
python -m pdf2docx convert input.pdf output.docx

# OCR locale per scan
ocrmypdf --skip-text --rotate-pages --deskew -l ita+eng input.pdf ocr.pdf

# DOCX → PDF per validazione
libreoffice --headless --convert-to pdf --outdir rendered output.docx

# Rendering pagine PDF a PNG, se disponibili i tool MuPDF
mutool draw -r 150 -o original-%d.png input.pdf
mutool draw -r 150 -o rendered-%d.png rendered/output.pdf
```

I comandi devono essere invocati da wrapper Python che gestiscono timeout, path sicuri, stderr, exit code e metadati dell'artefatto.

---

## Error handling e sicurezza

- Esegui tool esterni con `subprocess.run(..., shell=False, timeout=...)`.
- Non interpolare mai path o opzioni in shell string.
- Blocca PDF con dimensioni, pagine o decompression ratio oltre soglia.
- Usa workspace per-job e permessi minimi.
- Non rimuovere automaticamente password o protezioni: richiedi credenziali autorizzate.
- Mantieni una allowlist di formato input/output nella prima versione.
- Registra versioni dei binari e checksum dell'input per debug e riproducibilità.
- Tratta PDF non fidati come input potenzialmente malevolo: isola processi pesanti in container o sandbox quando il progetto cresce.

---

## Metriche da raccogliere

Per ogni job e per ogni pagina salva:

- Tempo per task e tempo totale.
- CPU/RAM massime se disponibili.
- Classe documento e decisioni di routing.
- Numero caratteri PDF, OCR e DOCX.
- Numero immagini, tabelle candidate, tabelle accettate e fallback raster.
- Similarità visiva, similarità testo e score tabelle.
- Font sostituiti e warning di overflow.
- Versioni engine/tool e configurazione completa.

Queste metriche sono indispensabili per confrontare regressioni e capire se un miglioramento di fedeltà giustifica un aumento del tempo di elaborazione.

---

## Limiti reali da accettare

- Un PDF non contiene sempre il modello logico originario: heading, liste, tabelle e reading order possono essere ambigui.
- Word può fare reflow diverso per font mancanti, metriche di font, stampante predefinita e versione di Office/LibreOffice.
- Forme vettoriali complesse, testo ruotato, trasparenze, clipping path, ligature e layout editoriali richiedono spesso fallback visuale.
- OCR non garantisce correttezza su scansioni degradate, timbri, scrittura manuale, codici e caratteri molto piccoli.
- L'obiettivo corretto non è “100% editabile e 100% identico” per ogni PDF, ma un sistema che massimizzi editabilità e fedeltà, quantifichi la qualità e degradi soltanto le regioni non affidabili.

---

## Decisione consigliata

Avvia il progetto con una pipeline a task locale e un engine baseline `pdf2docx`, aggiungendo OCRmyPDF solamente per documenti scannerizzati. Implementa subito il loop di validazione visuale/semantica: è il componente che permette di ottenere qualità pratica senza un engine commerciale. Successivamente sostituisci gradualmente `pdf2docx` con un parser proprietario basato su PyMuPDF, `layout.json` e un adapter OOXML, mantenendo invariati job, task, QA e storage.

---

## Fonti di design

- CloudConvert descrive una API organizzata in job e task, con operazioni di import, conversione ed export, workflow concatenabili, storage integration e modalità sincrona/asincrona.
- La pagina PDF to Office di CloudConvert dichiara la collaborazione con Apryse per conversioni PDF→Office ad alta precisione; questo progetto ne replica il pattern architetturale con componenti locali open-source.
- Il repository `pdf2docx` documenta una pipeline composta da estrazione con PyMuPDF, parsing rule-based del layout e generazione DOCX con `python-docx`; documenta inoltre supporto per layout, tabelle e immagini, insieme a limiti su PDF testuali, LTR e layout non perfettamente ricostruibili.

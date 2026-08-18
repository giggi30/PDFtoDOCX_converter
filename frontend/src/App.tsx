import { ChangeEvent, DragEvent, useEffect, useMemo, useState } from "react";

import {
  ConversionCreated,
  ConversionResult,
  ConversionStatus,
  createConversion,
  downloadResult,
  fetchArtifact,
  getConversion,
  getResult,
} from "./api/client";
import styles from "./App.module.css";

const phaseLabels: Record<string, string> = {
  VALIDATING: "Controllo del PDF",
  EXTRACTING: "Estrazione del contenuto",
  ANALYZING_LAYOUT: "Analisi del layout",
  BUILDING_DOCX: "Creazione del documento Word",
  RENDERING: "Preparazione delle anteprime",
  COMPARING: "Calcolo della qualità",
};

const ratingLabels = {
  excellent: "Eccellente",
  good: "Buona",
  fair: "Discreta",
  poor: "Da migliorare",
};

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [created, setCreated] = useState<ConversionCreated | null>(null);
  const [status, setStatus] = useState<ConversionStatus | null>(null);
  const [result, setResult] = useState<ConversionResult | null>(null);
  const [sourcePreviews, setSourcePreviews] = useState<string[]>([]);
  const [resultPreviews, setResultPreviews] = useState<string[]>([]);
  const [page, setPage] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const resetPreviewUrls = () => {
    sourcePreviews.forEach(URL.revokeObjectURL);
    resultPreviews.forEach(URL.revokeObjectURL);
    setSourcePreviews([]);
    setResultPreviews([]);
  };

  useEffect(() => {
    if (!created || status?.status === "COMPLETED" || status?.status === "FAILED") return;
    const poll = window.setInterval(async () => {
      try {
        setStatus(await getConversion(created.job_id, created.access_token));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Errore durante l'aggiornamento.");
        window.clearInterval(poll);
      }
    }, 900);
    return () => window.clearInterval(poll);
  }, [created, status?.status]);

  useEffect(() => {
    if (!created || status?.status !== "COMPLETED" || result) return;
    void (async () => {
      try {
        const quality = await getResult(created.job_id, created.access_token);
        const [sources, results] = await Promise.all([
          Promise.all(
            quality.source_preview_urls.map((url) => fetchArtifact(url, created.access_token)),
          ),
          Promise.all(
            quality.result_preview_urls.map((url) => fetchArtifact(url, created.access_token)),
          ),
        ]);
        setResult(quality);
        setSourcePreviews(sources);
        setResultPreviews(results);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Anteprime non disponibili.");
      }
    })();
  }, [created, result, status?.status]);

  useEffect(
    () => () => {
      sourcePreviews.forEach(URL.revokeObjectURL);
      resultPreviews.forEach(URL.revokeObjectURL);
    },
    [sourcePreviews, resultPreviews],
  );

  const pageCount = Math.max(sourcePreviews.length, resultPreviews.length);
  const expiresAt = useMemo(
    () => (created ? new Date(created.expires_at).toLocaleTimeString("it-IT") : null),
    [created],
  );

  const chooseFile = (selected: File | undefined) => {
    if (!selected) return;
    if (selected.type !== "application/pdf") {
      setError("Seleziona un file PDF.");
      return;
    }
    setFile(selected);
    setError(null);
  };

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    chooseFile(event.target.files?.[0]);
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files[0]);
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    resetPreviewUrls();
    setResult(null);
    try {
      const conversion = await createConversion(file);
      setCreated(conversion);
      setStatus({
        job_id: conversion.job_id,
        status: conversion.status,
        phase: null,
        progress: 0,
        warnings: [],
        error: null,
        expires_at: conversion.expires_at,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Caricamento non riuscito.");
    } finally {
      setBusy(false);
    }
  };

  const startOver = () => {
    resetPreviewUrls();
    setFile(null);
    setCreated(null);
    setStatus(null);
    setResult(null);
    setPage(0);
    setError(null);
  };

  return (
    <main className={styles.shell}>
      <header className={styles.header}>
        <a className={styles.brand} href="/" aria-label="CV Shift home">
          <span className={styles.brandMark}>C</span>
          <span>CV Shift</span>
        </a>
        <span className={styles.badge}>PDF → DOCX editabile</span>
      </header>

      <section className={styles.hero}>
        <p className={styles.eyebrow}>Conversione misurabile, non promesse vaghe</p>
        <h1>Il tuo CV in Word.<br />Con un punteggio di qualità.</h1>
        <p className={styles.lead}>
          Convertiamo CV PDF nativi in documenti modificabili e confrontiamo ogni pagina con
          l’originale. I file vengono eliminati entro 60 minuti.
        </p>
      </section>

      {!created && (
        <section className={styles.uploadCard} aria-labelledby="upload-title">
          <div className={styles.cardHeading}>
            <div>
              <span className={styles.step}>01</span>
              <h2 id="upload-title">Carica il curriculum</h2>
            </div>
            <span className={styles.limit}>PDF · max 10 MB · 5 pagine</span>
          </div>
          <label
            className={`${styles.dropzone} ${dragging ? styles.dragging : ""}`}
            onDragEnter={() => setDragging(true)}
            onDragLeave={() => setDragging(false)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <input type="file" accept="application/pdf,.pdf" onChange={handleFileInput} />
            <span className={styles.uploadIcon}>↑</span>
            <strong>{file ? file.name : "Trascina qui il tuo PDF"}</strong>
            <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "oppure scegli un file"}</span>
          </label>
          <div className={styles.controls}>
            <div />
            <button className={styles.primaryButton} disabled={!file || busy} onClick={submit}>
              {busy ? "Caricamento…" : "Converti il CV"}
            </button>
          </div>
        </section>
      )}

      {created && !result && (
        <section className={styles.progressCard} aria-live="polite">
          <span className={styles.step}>02</span>
          <p className={styles.eyebrow}>Conversione in corso</p>
          <h2>{status?.phase ? phaseLabels[status.phase] ?? status.phase : "In attesa del worker"}</h2>
          <div className={styles.progressTrack}>
            <span style={{ width: `${status?.progress ?? 0}%` }} />
          </div>
          <div className={styles.progressMeta}>
            <span>{status?.progress ?? 0}%</span>
            <span>Disponibile fino alle {expiresAt}</span>
          </div>
          {status?.status === "FAILED" && (
            <button className={styles.secondaryButton} onClick={startOver}>Riprova</button>
          )}
        </section>
      )}

      {result && (
        <>
          <section className={styles.scoreCard}>
            <div className={styles.scoreHero}>
              <span className={styles.step}>03</span>
              <p className={styles.eyebrow}>Analisi completata</p>
              <div className={styles.scoreLine}>
                <strong>{result.overall_score?.toFixed(0)}</strong>
                <span>/100<br />{result.rating ? ratingLabels[result.rating] : ""}</span>
              </div>
            </div>
            {result.metrics && (
              <div className={styles.metrics}>
                {[
                  ["Testo", result.metrics.text_accuracy],
                  ["Layout", result.metrics.layout_similarity],
                  ["Resa visiva", result.metrics.visual_similarity],
                  ["Pagine", result.metrics.page_count_match],
                ].map(([label, value]) => (
                  <div className={styles.metric} key={label}>
                    <span>{label}</span><strong>{Number(value).toFixed(0)}%</strong>
                    <i><b style={{ width: `${value}%` }} /></i>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className={styles.compareSection}>
            <div className={styles.sectionHeading}>
              <div><span className={styles.step}>04</span><h2>Confronto pagina per pagina</h2></div>
              <div className={styles.pagination}>
                <button disabled={page === 0} onClick={() => setPage((value) => value - 1)}>←</button>
                <span>{page + 1} / {pageCount}</span>
                <button disabled={page + 1 >= pageCount} onClick={() => setPage((value) => value + 1)}>→</button>
              </div>
            </div>
            <div className={styles.previews}>
              <figure><figcaption>PDF originale</figcaption>{sourcePreviews[page] && <img src={sourcePreviews[page]} alt={`Pagina ${page + 1} del PDF`} />}</figure>
              <figure><figcaption>DOCX generato</figcaption>{resultPreviews[page] && <img src={resultPreviews[page]} alt={`Pagina ${page + 1} del DOCX`} />}</figure>
            </div>
          </section>

          <section className={styles.findings}>
            <div><span className={styles.step}>05</span><h2>Differenze rilevate</h2></div>
            <ul>{result.differences.map((difference) => <li key={difference}>{difference}</li>)}</ul>
            {!!status?.warnings.length && <ul>{status.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
          </section>

          <section className={styles.actions}>
            <div><strong>Il documento è pronto.</strong><span>Ricontrolla il risultato in Word prima di inviarlo.</span></div>
            <div>
              <button className={styles.secondaryButton} onClick={startOver}>Nuova conversione</button>
              <button
                className={styles.primaryButton}
                onClick={() => {
                  if (created) void downloadResult(created.job_id, created.access_token);
                }}
              >
                Scarica DOCX
              </button>
            </div>
          </section>
        </>
      )}

      {error && <div className={styles.error} role="alert">{error}</div>}
      <footer>CV Shift · Nessun account · Cancellazione automatica entro 60 minuti</footer>
    </main>
  );
}

export default App;

import { useRef, useState } from "react";
import * as XLSX from "xlsx";

const IMAGE_TYPES   = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const EXCEL_EXTS    = [".xlsx", ".xls", ".csv"];
const DEFAULT_PROMPT = "A cinematic, smooth video transition";

function parseSpreadsheet(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const wb   = XLSX.read(data, { type: "array" });
        const ws   = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });
        const map  = {};
        for (let i = 1; i < rows.length; i++) {
          const name   = String(rows[i][0] || "").trim();
          const prompt = String(rows[i][1] || "").trim();
          if (name && prompt) {
            const k = name.toLowerCase();
            if (!map[k]) map[k] = [];
            map[k].push(prompt);
          }
        }
        resolve(map);
      } catch {
        resolve({});
      }
    };
    reader.readAsArrayBuffer(file);
  });
}

export { parseSpreadsheet };

export function applyMapToImages(prev, map) {
  const result = [];
  for (const entry of prev) {
    const arr = map[entry.file.name.toLowerCase()];
    if (!arr) { result.push(entry); continue; }
    const dot  = entry.file.name.lastIndexOf(".");
    const stem = dot >= 0 ? entry.file.name.slice(0, dot) : entry.file.name;
    const ext  = dot >= 0 ? entry.file.name.slice(dot)    : "";
    arr.forEach((p, i) => {
      const newName = i === 0 ? entry.file.name : `${stem}_p${i + 1}${ext}`;
      const newFile = i === 0 ? entry.file : new File([entry.file], newName, { type: entry.file.type });
      result.push({ ...entry, id: i === 0 ? entry.id : Math.random().toString(36).slice(2), file: newFile, preview: entry.preview, prompt: p });
    });
  }
  return result;
}

export default function ImageUploader({ images, onImagesChange }) {
  const imgInputRef    = useRef(null);
  const excelInputRef  = useRef(null);
  const [drag,         setDrag]         = useState(false);
  const [excelInfo,    setExcelInfo]    = useState(null);

  const addImages = (files) => {
    const valid = Array.from(files).filter((f) => IMAGE_TYPES.includes(f.type));
    if (!valid.length) return;
    const entries = valid.map((file) => ({
      id:      Math.random().toString(36).slice(2),
      file,
      preview: URL.createObjectURL(file),
      prompt:  DEFAULT_PROMPT,
    }));
    onImagesChange((prev) => {
      const existing = new Set(prev.map((e) => e.file.name + e.file.size));
      return [...prev, ...entries.filter((e) => !existing.has(e.file.name + e.file.size))];
    });
  };

  const applyExcel = async (file) => {
    const map   = await parseSpreadsheet(file);
    const count = Object.values(map).reduce((s, arr) => s + arr.length, 0);
    setExcelInfo({ name: file.name, count });
    onImagesChange((prev) => applyMapToImages(prev, map));
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    setDrag(false);
    const files  = Array.from(e.dataTransfer.files);
    const imgs   = files.filter((f) => IMAGE_TYPES.includes(f.type));
    const sheets = files.filter((f) => EXCEL_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext)));
    if (imgs.length)   addImages(imgs);
    if (sheets.length) await applyExcel(sheets[0]);
  };

  const removeImage = (id) => {
    onImagesChange((prev) => {
      const entry = prev.find((e) => e.id === id);
      if (entry) URL.revokeObjectURL(entry.preview);
      return prev.filter((e) => e.id !== id);
    });
  };

  const updatePrompt = (id, prompt) => {
    onImagesChange((prev) => prev.map((e) => (e.id === id ? { ...e, prompt } : e)));
  };

  return (
    <div>
      {/* Drop zone */}
      <div
        className={`upload-zone${drag ? " drag" : ""}`}
        onClick={() => imgInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={handleDrop}
      >
        <div className="upload-icon-wrap">🖼️</div>
        <div className="upload-main">Arrastrá imágenes aquí o hacé clic para seleccionar</div>
        <div className="upload-hint">JPG, PNG, WEBP — podés arrastrar imágenes + Excel/CSV juntos</div>
        <input
          ref={imgInputRef} type="file" multiple
          accept={IMAGE_TYPES.join(",")}
          style={{ display: "none" }}
          onChange={(e) => { addImages(e.target.files); e.target.value = ""; }}
        />
      </div>

      {/* Excel/CSV loader */}
      <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10 }}>
        <button
          className="btn-excel"
          onClick={() => excelInputRef.current?.click()}
          disabled={!images.length}
          type="button"
        >
          📊 Cargar prompts desde Excel / CSV
        </button>
        {excelInfo && (
          <span className="excel-badge">
            ✓ {excelInfo.name} — {excelInfo.count} prompt{excelInfo.count !== 1 ? "s" : ""} cargado{excelInfo.count !== 1 ? "s" : ""}
          </span>
        )}
        <input ref={excelInputRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }}
          onChange={async (e) => { if (e.target.files[0]) await applyExcel(e.target.files[0]); e.target.value = ""; }}
        />
      </div>

      {/* Image list */}
      {images.length > 0 && (
        <div className="image-list">
          {images.map((entry) => (
            <div key={entry.id} className="image-row">
              <img src={entry.preview} alt={entry.file.name} className="image-thumb" />
              <div className="image-info">
                <div className="image-name">{entry.file.name}</div>
                <textarea
                  className="image-prompt-input"
                  value={entry.prompt}
                  onChange={(e) => updatePrompt(entry.id, e.target.value)}
                  placeholder="Describe el video que querés generar..."
                  rows={2}
                />
              </div>
              <button className="image-remove-btn" onClick={() => removeImage(entry.id)} title="Quitar">✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

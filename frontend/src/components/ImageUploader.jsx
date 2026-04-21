import { useRef, useState } from "react";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const DEFAULT_PROMPT = "A cinematic, smooth video transition";

export default function ImageUploader({ images, onImagesChange }) {
  const inputRef  = useRef(null);
  const [drag, setDrag] = useState(false);

  const addFiles = (files) => {
    const valid = Array.from(files).filter((f) => ACCEPTED.includes(f.type));
    if (!valid.length) return;

    const entries = valid.map((file) => ({
      id:     Math.random().toString(36).slice(2),
      file,
      preview: URL.createObjectURL(file),
      prompt:  DEFAULT_PROMPT,
    }));

    onImagesChange((prev) => {
      // avoid duplicates by name+size
      const existing = new Set(prev.map((e) => e.file.name + e.file.size));
      return [...prev, ...entries.filter((e) => !existing.has(e.file.name + e.file.size))];
    });
  };

  const removeImage = (id) => {
    onImagesChange((prev) => {
      const entry = prev.find((e) => e.id === id);
      if (entry) URL.revokeObjectURL(entry.preview);
      return prev.filter((e) => e.id !== id);
    });
  };

  const updatePrompt = (id, prompt) => {
    onImagesChange((prev) => prev.map((e) => e.id === id ? { ...e, prompt } : e));
  };

  return (
    <div>
      {/* Drop zone */}
      <div
        className={`upload-zone${drag ? " drag" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
      >
        <div className="upload-icon-wrap">🖼️</div>
        <div className="upload-main">Arrastrá imágenes aquí o hacé clic para seleccionar</div>
        <div className="upload-hint">JPG, PNG, WEBP, GIF — podés subir varias a la vez</div>
        <input
          ref={inputRef} type="file" multiple accept={ACCEPTED.join(",")}
          style={{ display: "none" }}
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {/* Image list with per-image prompt */}
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

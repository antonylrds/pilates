import { type FormEvent, useEffect, useRef, useState } from "react";

import { api, authFetch, call, errorMessage } from "../lib/api";
import { fmtDateTime } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useSession } from "../lib/session";
import { ConfirmPanel } from "./ConfirmPanel";
import { Modal } from "./Modal";
import { Empty, ErrorBox, Loading } from "./ui";

type Props = { studentId: number; version: number };

const ACCEPT = "application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png";

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Laudos e outros documentos do aluno. Todos consultam e baixam; só o admin envia e apaga. */
export function StudentDocuments({ studentId, version }: Props) {
  const { isAdmin } = useSession();
  const list = useAsync(
    () => call(api.GET("/api/v1/students/{student_id}/documents", { params: { path: { student_id: studentId } } })),
    [studentId, version],
  );
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File>();
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [removing, setRemoving] = useState<number>();
  const [editing, setEditing] = useState<{ id: number; text: string }>();
  const [preview, setPreview] = useState<{ url: string; filename: string; type: string }>();

  // Libera o arquivo da memória quando a pré-visualização fecha (ou troca).
  useEffect(() => {
    const url = preview?.url;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [preview?.url]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(undefined);
    try {
      const body = new FormData();
      body.append("file", file);
      if (description.trim()) body.append("description", description.trim());
      const response = await authFetch(`/api/v1/students/${studentId}/documents`, { method: "POST", body });
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => undefined)));
      setFile(undefined);
      setDescription("");
      if (fileInput.current) fileInput.current.value = "";
      list.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function download(id: number, filename: string) {
    setError(undefined);
    try {
      const response = await authFetch(`/api/v1/students/${studentId}/documents/${id}/download`);
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => undefined)));
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  /** Mostra o arquivo (imagem ou PDF) num modal, sem sair da página. */
  async function view(id: number, filename: string) {
    setError(undefined);
    try {
      const response = await authFetch(`/api/v1/students/${studentId}/documents/${id}/download`);
      if (!response.ok) throw new Error(errorMessage(await response.json().catch(() => undefined)));
      const blob = await response.blob();
      setPreview({ url: URL.createObjectURL(blob), filename, type: blob.type });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function saveDescription() {
    if (!editing) return;
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.PATCH("/api/v1/students/{student_id}/documents/{document_id}", {
          params: { path: { student_id: studentId, document_id: editing.id } },
          body: { description: editing.text.trim() || null },
        }),
      );
      setEditing(undefined);
      list.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setBusy(true);
    setError(undefined);
    try {
      await call(
        api.DELETE("/api/v1/students/{student_id}/documents/{document_id}", {
          params: { path: { student_id: studentId, document_id: id } },
        }),
      );
      setRemoving(undefined);
      list.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const docs = list.data ?? [];

  return (
    <div className="card">
      <h3 className="card-title">
        Documentos <span className="muted small">(laudos e exames · PDF, JPG ou PNG até 10 MB)</span>
      </h3>

      {isAdmin && (
        <form className="form-row" onSubmit={upload}>
          <label className="field">
            <span>Arquivo</span>
            <input
              ref={fileInput}
              type="file"
              accept={ACCEPT}
              onChange={(e) => setFile(e.target.files?.[0])}
              required
            />
          </label>
          <label className="field">
            <span>Descrição (opcional)</span>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              placeholder="Ex.: Laudo ortopédico, 03/2026"
            />
          </label>
          <div className="field">
            <span>&nbsp;</span>
            <button type="submit" className="btn btn-primary" disabled={busy || !file}>
              Enviar
            </button>
          </div>
        </form>
      )}

      {error && <ErrorBox message={error} />}
      {list.loading && !list.data && <Loading />}
      {list.error && <ErrorBox message={list.error} />}
      {list.data && docs.length === 0 && <Empty>Nenhum documento anexado.</Empty>}

      {docs.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Arquivo</th>
                <th>Descrição</th>
                <th>Enviado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div className="doc-name" title={d.filename}>
                      {d.filename}
                    </div>
                    <div className="muted small">{fmtSize(d.size)}</div>
                  </td>
                  <td className="small">
                    {editing?.id === d.id ? (
                      <form
                        className="toolbar"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void saveDescription();
                        }}
                      >
                        <input
                          value={editing.text}
                          onChange={(e) => setEditing({ id: d.id, text: e.target.value })}
                          maxLength={500}
                          placeholder="Ex.: Laudo ortopédico, 03/2026"
                          aria-label="Descrição do documento"
                          autoFocus
                        />
                        <button type="submit" className="btn btn-sm btn-primary" disabled={busy}>
                          Salvar
                        </button>
                        <button type="button" className="btn btn-sm btn-ghost" onClick={() => setEditing(undefined)}>
                          Cancelar
                        </button>
                      </form>
                    ) : (
                      <>
                        {d.description || <span className="muted">—</span>}
                        {isAdmin && (
                          <button
                            className="link-button"
                            onClick={() => setEditing({ id: d.id, text: d.description ?? "" })}
                          >
                            {" "}
                            {d.description ? "editar" : "adicionar descrição"}
                          </button>
                        )}
                      </>
                    )}
                  </td>
                  <td className="small">
                    {fmtDateTime(d.created_at)}
                    <div className="muted">{d.uploaded_by_name}</div>
                  </td>
                  <td>
                    <div className="toolbar">
                      <button className="btn btn-sm btn-primary" onClick={() => view(d.id, d.filename)}>
                        Visualizar
                      </button>
                      <button className="btn btn-sm" onClick={() => download(d.id, d.filename)}>
                        Baixar
                      </button>
                      {isAdmin && (
                        <button className="btn btn-sm btn-ghost" onClick={() => setRemoving(d.id)}>
                          Excluir
                        </button>
                      )}
                    </div>
                    {removing === d.id && (
                      <ConfirmPanel
                        title="Excluir documento"
                        confirmLabel="Excluir"
                        tone="danger"
                        busy={busy}
                        onConfirm={() => remove(d.id)}
                        onCancel={() => setRemoving(undefined)}
                      >
                        <p>
                          <strong>{d.filename}</strong> será apagado definitivamente.
                        </p>
                      </ConfirmPanel>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {preview && (
        <Modal title={preview.filename} onClose={() => setPreview(undefined)} wide>
          {preview.type.startsWith("image/") ? (
            <img className="doc-preview-image" src={preview.url} alt={preview.filename} />
          ) : (
            <iframe className="doc-preview-frame" src={preview.url} title={preview.filename} />
          )}
        </Modal>
      )}
    </div>
  );
}

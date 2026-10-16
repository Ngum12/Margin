import { Attendance } from "../components/Attendance";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { api } from "../api/endpoints";
import type { CoverSheetRow, ExamDetail, ScanPage, ScriptsOverview, Upload } from "../api/types";
import { errorMessage } from "../components/errors";
import { ErrorMessage, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { Icon } from "../components/Icon";
import { ExamHeader } from "../exam/ExamHeader";

const POLL_MS = 3000;

interface ScanData {
  exam: ExamDetail;
  uploads: Upload[];
  overview: ScriptsOverview;
  tray: ScanPage[];
  students: CoverSheetRow[];
}

async function loadAll(examId: number): Promise<ScanData> {
  const [exam, uploads, overview, tray, students] = await Promise.all([
    api.exam(examId),
    api.uploads(examId),
    api.scripts(examId),
    api.tray(examId),
    api.coverSheets(examId),
  ]);
  return { exam, uploads, overview, tray, students };
}

export default function Scans() {
  const { t } = useTranslation();
  const examId = Number(useParams().examId);
  const { state, reload } = useLoad(() => loadAll(examId), [examId]);
  const data = state.status === "ready" ? state.data : null;
  const refresh = reload;

  useEffect(() => {
    const timer = window.setInterval(refresh, POLL_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [refresh]);

  if (state.status === "error") return <ErrorMessage error={state.error} />;
  if (!data) return <Loading />;
  const filenames = new Map(data.uploads.map((u) => [u.id, u.original_filename]));

  return (
    <section>
      <ExamHeader exam={data.exam} />
      <Attendance examId={examId} />
      {data.exam.status === "draft" ? (
        <p className="panel empty-state">{t("sheets.needReady")}</p>
      ) : (
        <>
          <UploadPanel examId={examId} onUploaded={refresh} />
          <UploadList uploads={data.uploads} onChange={refresh} />
          <Tray
            examId={examId}
            pages={data.tray}
            filenames={filenames}
            students={data.students}
            onChange={refresh}
          />
          <ScriptList
            examId={examId}
            overview={data.overview}
            filenames={filenames}
            onChange={refresh}
          />
        </>
      )}
    </section>
  );
}

function UploadPanel({ examId, onUploaded }: { examId: number; onUploaded: () => void }) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<{ name: string; text: string; ok: boolean }[]>([]);
  const [uploading, setUploading] = useState(false);

  async function upload(files: File[]) {
    setUploading(true);
    setMessages([]);
    for (const file of files) {
      try {
        await api.uploadScan(examId, file);
        setMessages((m) => [...m, { name: file.name, text: t("scans.uploaded"), ok: true }]);
      } catch (err) {
        setMessages((m) => [...m, { name: file.name, text: errorMessage(t, err), ok: false }]);
      }
      onUploaded();
    }
    setUploading(false);
  }

  return (
    <div className="panel">
      <h2>{t("scans.uploadTitle")}</h2>
      <p className="muted">{t("scans.uploadHelp")}</p>
      <div className="upload-drop">
        <input
          type="file"
          accept="application/pdf,.pdf"
          multiple
          disabled={uploading}
          aria-label={t("scans.choose")}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length > 0) void upload(files);
          }}
        />
      </div>
      {uploading && (
        <p className="muted" role="status">
          {t("scans.uploading")}
        </p>
      )}
      <ul className="plain-list">
        {messages.map((m) => (
          <li key={m.name} className={m.ok ? "success" : "error"} role={m.ok ? "status" : "alert"}>
            {m.name}: {m.text}
          </li>
        ))}
      </ul>
    </div>
  );
}

function UploadList({ uploads, onChange }: { uploads: Upload[]; onChange: () => void }) {
  const { t, i18n } = useTranslation();
  const [error, setError] = useState<unknown>(null);
  if (uploads.length === 0) return null;
  return (
    <div className="table-wrap card-table">
      <ErrorMessage error={error} />
      <table className="data-table">
        <thead>
          <tr>
            <th>{t("scans.file")}</th>
            <th>{t("scans.uploadedAt")}</th>
            <th className="num">{t("scans.pages")}</th>
            <th>{t("exam.status")}</th>
            <th>{t("common.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {uploads.map((u) => (
            <tr key={u.id}>
              <td>{u.original_filename}</td>
              <td>{new Date(u.created_at).toLocaleString(i18n.language)}</td>
              <td className="num">{u.page_count ?? "—"}</td>
              <td>
                <span className={`badge badge-upload-${u.status}`}>
                  {t(`scans.uploadStatus.${u.status}`)}
                </span>
                {u.error_code && (
                  <div className="error">
                    {t(`errors.${u.error_code}`, { defaultValue: t("errors.generic") })}
                  </div>
                )}
              </td>
              <td className="row-actions">
                <a href={api.originalUrl(u.id)}>
                  <Icon name="download" size={16} /> {t("scans.original")}
                </a>
                {u.status === "failed" && (
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      setError(null);
                      api.retryUpload(u.id).then(onChange).catch(setError);
                    }}
                  >
                    {t("scans.retry")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PageThumb({ page, filenames }: { page: ScanPage; filenames: Map<number, string> }) {
  const { t } = useTranslation();
  const label = t("scans.pageOf", {
    number: page.source_page_index + 1,
    file: filenames.get(page.upload_id) ?? "",
  });
  return (
    <a href={api.pageImageUrl(page.id, "full")} target="_blank" rel="noreferrer" className="thumb">
      <img src={api.pageImageUrl(page.id)} alt={label} loading="lazy" />
    </a>
  );
}

function Tray({
  examId,
  pages,
  filenames,
  students,
  onChange,
}: {
  examId: number;
  pages: ScanPage[];
  filenames: Map<number, string>;
  students: CoverSheetRow[];
  onChange: () => void;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [studentId, setStudentId] = useState("");
  const [error, setError] = useState<unknown>(null);

  if (pages.length === 0) return null;

  function toggle(page: ScanPage, checked: boolean) {
    const next = new Set(selected);
    // Selecting a problem cover also selects the pages that follow it.
    const group = [page, ...pages.filter((p) => p.related_page_id === page.id)];
    for (const p of group) {
      if (checked) next.add(p.id);
      else next.delete(p.id);
    }
    setSelected(next);
  }

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setSelected(new Set());
      onChange();
    } catch (err) {
      setError(err);
    }
  }

  const ids = [...selected];
  return (
    <div className="panel tray">
      <h2>
        {t("scans.trayTitle", { count: pages.filter((p) => p.state === "unassigned").length })}
      </h2>
      <p className="muted">{t("scans.trayHelp")}</p>
      <div className="actions tray-actions">
        <select
          aria-label={t("scans.assignTo")}
          value={studentId}
          onChange={(e) => {
            setStudentId(e.target.value);
          }}
        >
          <option value="">{t("scans.assignTo")}</option>
          {students.map((s) => (
            <option key={s.student_id} value={s.student_id}>
              {s.code}
              {s.display_name ? ` — ${s.display_name}` : ""}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={ids.length === 0 || !studentId}
          onClick={() => void act(() => api.assignPages(examId, ids, Number(studentId)))}
        >
          {t("scans.assign", { count: ids.length })}
        </button>
        <button
          type="button"
          className="button-secondary"
          disabled={ids.length === 0}
          onClick={() => void act(() => api.discardPages(examId, ids))}
        >
          {t("scans.discard")}
        </button>
      </div>
      <ErrorMessage error={error} />
      <ul className="page-grid">
        {pages.map((page) => (
          <li
            key={page.id}
            className={page.state === "discarded" ? "page-card discarded" : "page-card"}
          >
            <label className="checkbox">
              <input
                type="checkbox"
                checked={selected.has(page.id)}
                onChange={(e) => {
                  toggle(page, e.target.checked);
                }}
              />
              <span>
                {t("scans.pageOf", {
                  number: page.source_page_index + 1,
                  file: filenames.get(page.upload_id) ?? "",
                })}
              </span>
            </label>
            <PageThumb page={page} filenames={filenames} />
            <p className={page.state === "discarded" ? "reason" : "reason reason-flag"}>
              {page.state !== "discarded" && <Icon name="warning" size={14} />}
              <span>
                {page.state === "discarded"
                  ? t("scans.discarded")
                  : page.unassigned_reason
                    ? t(`scans.reason.${page.unassigned_reason}`)
                    : ""}
                {page.detected_exam_title && ` (${page.detected_exam_title})`}
              </span>
            </p>
            {page.state === "discarded" ? (
              <button
                type="button"
                className="button-secondary button-small"
                onClick={() => void act(() => api.unassignPages(examId, [page.id]))}
              >
                <Icon name="undo" size={16} />
                {t("scans.restore")}
              </button>
            ) : (
              <button
                type="button"
                className="button-quiet button-small"
                aria-label={t("scans.discardOne", {
                  number: page.source_page_index + 1,
                  file: filenames.get(page.upload_id) ?? "",
                })}
                onClick={() => void act(() => api.discardPages(examId, [page.id]))}
              >
                <Icon name="trash" size={16} />
                {t("scans.discardShort")}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ScriptList({
  examId,
  overview,
  filenames,
  onChange,
}: {
  examId: number;
  overview: ScriptsOverview;
  filenames: Map<number, string>;
  onChange: () => void;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<unknown>(null);

  return (
    <div className="panel">
      <h2>
        {t("scans.scriptsTitle", {
          count: overview.scripts.length,
          total: overview.scripts.length + overview.missing.length,
        })}
      </h2>
      <ErrorMessage error={error} />
      {overview.scripts.length === 0 && <p className="empty-state">{t("scans.noScripts")}</p>}
      {overview.scripts.length > 0 && (
        <ul className="script-rows">
          {overview.scripts.map((script) => (
            <li key={script.id} className="script-row">
              <div className="script-row-who">
                <span className="script-row-name">
                  {script.student.display_name ?? (
                    <span className="code">{script.student.code}</span>
                  )}
                </span>
                {script.student.display_name && (
                  <>
                    <span className="code">{script.student.code}</span>{" "}
                  </>
                )}
                <span className="muted small">
                  {t("scans.pageCount", { count: script.pages.length })}
                </span>
                {script.page_count_flag && (
                  <p className="warning-text">
                    {t(`scans.pageFlag.${script.page_count_flag}`, {
                      typical: overview.typical_page_count ?? "?",
                    })}
                  </p>
                )}
              </div>
              <ol className="script-row-pages" aria-label={script.student.code}>
                {script.pages.map((page) => (
                  <li key={page.id}>
                    <PageThumb page={page} filenames={filenames} />
                    <span className="muted small">
                      {t("scans.position", { number: page.position })}
                    </span>
                    <button
                      type="button"
                      className="button-quiet button-small"
                      aria-label={t("scans.returnPage", {
                        number: page.position,
                        code: script.student.code,
                      })}
                      title={t("scans.returnToTray")}
                      onClick={() => {
                        setError(null);
                        api.unassignPages(examId, [page.id]).then(onChange).catch(setError);
                      }}
                    >
                      <Icon name="undo" size={16} />
                      {t("scans.returnShort")}
                    </button>
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ul>
      )}
      {overview.missing.length > 0 && (
        <>
          <h3>{t("scans.missingTitle", { count: overview.missing.length })}</h3>
          <p className="muted">
            {overview.missing
              .map((s) => (s.display_name ? `${s.code} (${s.display_name})` : s.code))
              .join(", ")}
          </p>
        </>
      )}
    </div>
  );
}

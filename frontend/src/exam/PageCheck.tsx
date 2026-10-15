import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints";
import type { PageCheck as PageCheckData } from "../api/types";
import { ErrorMessage } from "../components/ui";
import { rotate } from "../review/viewer";

/** Step before AI marking (owner, 2026-10-15): look at every page and turn any that are not
 * upright. The reading model cannot tell which way up a page is, and an upside-down page costs
 * marks. AI marking is allowed once the pages are checked. */
export function PageCheck({
  data,
  onChange,
}: {
  data: PageCheckData;
  onChange: (data: PageCheckData) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(data.checked_at === null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const pages = data.scripts.reduce((sum, s) => sum + s.pages.length, 0);
  if (data.scripts.length === 0) return null;

  async function act(call: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await call();
      onChange(await api.pageCheck(data.exam_id));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      onChange(await api.confirmPageCheck(data.exam_id));
      setOpen(false);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" id="page-check">
      <div className="question-head">
        <h2>{t("pageCheck.title")}</h2>
        {data.checked_at && (
          <span className="badge badge-script-confirmed">
            {t("pageCheck.checkedOn", { date: new Date(data.checked_at).toLocaleString() })}
          </span>
        )}
      </div>
      <p className="muted">{t("pageCheck.help", { count: pages })}</p>
      {!open ? (
        <button
          type="button"
          className="button-secondary"
          onClick={() => {
            setOpen(true);
          }}
        >
          {t("pageCheck.show")}
        </button>
      ) : (
        <>
          <div className="page-check">
            {data.scripts.map((script) => (
              <section key={script.script_id} className="page-check-script">
                <h3>
                  {script.student_name ?? "—"} <span className="code">{script.student_code}</span>
                </h3>
                <ol className="page-check-pages">
                  {script.pages.map((page, index) => (
                    <li key={page.id}>
                      <div className="page-check-thumb">
                        <img
                          src={api.pageImageUrl(page.id, "thumb")}
                          alt={t("pageCheck.pageAlt", {
                            code: script.student_code,
                            page: index + 1,
                          })}
                          data-rotation={page.rotation}
                          loading="lazy"
                          style={{ transform: `rotate(${String(page.rotation)}deg)` }}
                        />
                      </div>
                      <span className="muted small">
                        {page.is_cover
                          ? t("review.viewer.coverThumb")
                          : t("review.viewer.pageThumb", { page: index + 1 })}
                      </span>
                      <span className="page-check-actions">
                        <button
                          type="button"
                          className="button-secondary"
                          disabled={busy}
                          aria-label={t("pageCheck.rotateLeft", {
                            code: script.student_code,
                            page: index + 1,
                          })}
                          onClick={() =>
                            void act(() => api.rotatePage(page.id, rotate(page.rotation, -90)))
                          }
                        >
                          ⟲
                        </button>
                        <button
                          type="button"
                          className="button-secondary"
                          disabled={busy}
                          aria-label={t("pageCheck.rotateRight", {
                            code: script.student_code,
                            page: index + 1,
                          })}
                          onClick={() =>
                            void act(() => api.rotatePage(page.id, rotate(page.rotation, 90)))
                          }
                        >
                          ⟳
                        </button>
                      </span>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void confirm()}>
              {t("pageCheck.confirm")}
            </button>
          </div>
        </>
      )}
      <ErrorMessage error={error} />
    </div>
  );
}

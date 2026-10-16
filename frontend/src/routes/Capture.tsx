import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { request } from "../api/client";
import { ErrorMessage, Field } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { ScanInbox } from "../components/ScanInbox";

type Options = {
  left: number;
  top: number;
  right: number;
  bottom: number;
  angle: number;
  auto_crop: boolean;
  auto_straighten: boolean;
  clean: boolean;
};
type Capture = {
  id: number;
  status: string;
  error_code: string | null;
  options: Options;
  prepared: boolean;
};
export default function CapturePage() {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => request<Capture[]>("GET", "/api/capture"), []);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => {
    const timer = setInterval(reload, 3000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  async function send(file: File) {
    setError(null);
    setBusy(true);
    const suffix = file.name.includes(".")
      ? `.${file.name.split(".").pop()?.toLowerCase() ?? "jpg"}`
      : file.type === "image/png"
        ? ".png"
        : ".jpg";
    try {
      const capture = await request<Capture>(
        "POST",
        `/api/capture?suffix=${encodeURIComponent(suffix)}`,
        { file },
      );
      setSelected(capture.id);
      reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  const captures = state.status === "ready" ? state.data.filter((c) => c.status !== "removed") : [];
  const current = captures.find((c) => c.id === selected) ?? captures[0];
  return (
    <section className="capture-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("capture.eyebrow")}</p>
          <h1>{t("capture.title")}</h1>
          <p className="page-lede">{t("capture.help")}</p>
        </div>
        <Link className="button-secondary" to="/">
          {t("capture.desk")}
        </Link>
      </header>
      <div className="panel">
        <Field label={t("capture.take")}>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/tiff"
            capture="environment"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void send(file);
              event.target.value = "";
            }}
          />
        </Field>
        <p className="field-hint">{t("capture.limit")}</p>
        {busy && <p role="status">{t("capture.sending")}</p>}
        <ErrorMessage error={error} />
      </div>
      {state.status === "error" && <ErrorMessage error={state.error} />}
      {captures.length > 0 && (
        <Field label={t("capture.recent")}>
          <select
            value={current?.id ?? ""}
            onChange={(e) => {
              setSelected(Number(e.target.value));
            }}
          >
            {captures.map((c) => (
              <option value={c.id} key={c.id}>
                {c.id} · {t(`capture.status.${c.status}`)}
              </option>
            ))}
          </select>
        </Field>
      )}
      {current && <Preparation key={current.id} capture={current} reload={reload} />}
      <ScanInbox />
    </section>
  );
}
function Preparation({ capture, reload }: { capture: Capture; reload: () => void }) {
  const { t } = useTranslation();
  const [options, setOptions] = useState(capture.options);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  function change(patch: Partial<Options>) {
    setOptions((value) => ({ ...value, ...patch }));
    setDirty(true);
  }
  async function run(action: () => Promise<unknown>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      setDirty(false);
      reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  const editable = ["capture_preview", "quarantine"].includes(capture.status);
  const url = `/api/capture/${String(capture.id)}/image`;
  return (
    <div className="panel">
      <h2>{t(`capture.status.${capture.status}`)}</h2>
      {capture.error_code && <p className="error">{t(`errors.${capture.error_code}`)}</p>}
      {capture.prepared && (
        <div className="capture-comparison">
          <figure>
            <figcaption>{t("capture.original")}</figcaption>
            <div className="capture-original">
              <img src={`${url}?original=true`} alt={t("capture.original")} />
              <span
                className="capture-crop-outline"
                style={{
                  left: `${String(options.left * 100)}%`,
                  top: `${String(options.top * 100)}%`,
                  right: `${String((1 - options.right) * 100)}%`,
                  bottom: `${String((1 - options.bottom) * 100)}%`,
                }}
              />
            </div>
          </figure>
          <figure>
            <figcaption>{t("capture.prepared")}</figcaption>
            <img
              src={`${url}?v=${encodeURIComponent(JSON.stringify(capture.options))}`}
              alt={t("capture.prepared")}
            />
          </figure>
        </div>
      )}
      {editable && (
        <>
          <p>{t("capture.check")}</p>
          <details>
            <summary>{t("capture.adjust")}</summary>
            <div className="form-row">
              {(["left", "top", "right", "bottom"] as const).map((key) => (
                <Field label={t(`capture.${key}`)} key={key}>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={Math.round(options[key] * 100)}
                    onChange={(e) => {
                      change({ [key]: Number(e.target.value) / 100, auto_crop: false });
                    }}
                  />
                </Field>
              ))}
              <Field label={t("capture.angle")}>
                <input
                  type="number"
                  min={-15}
                  max={15}
                  step={0.5}
                  value={options.angle}
                  onChange={(e) => {
                    change({ angle: Number(e.target.value) });
                  }}
                />
              </Field>
            </div>
            {(["auto_crop", "auto_straighten", "clean"] as const).map((key) => (
              <label className="checkbox" key={key}>
                <input
                  type="checkbox"
                  checked={options[key]}
                  onChange={(e) => {
                    change({ [key]: e.target.checked });
                  }}
                />
                {t(`capture.${key}`)}
              </label>
            ))}
            <button
              type="button"
              className="button-secondary"
              disabled={busy || !dirty}
              onClick={() =>
                void run(() =>
                  request("PUT", `/api/capture/${String(capture.id)}/options`, { json: options }),
                )
              }
            >
              {t("capture.preview")}
            </button>
          </details>
          <div className="actions">
            <button
              type="button"
              disabled={busy || dirty || capture.status !== "capture_preview"}
              onClick={() =>
                void run(() => request("POST", `/api/capture/${String(capture.id)}/accept`))
              }
            >
              {t("capture.accept")}
            </button>
            <button
              type="button"
              className="button-quiet"
              disabled={busy}
              onClick={() =>
                void run(() => request("POST", `/api/capture/${String(capture.id)}/discard`))
              }
            >
              {t("capture.discard")}
            </button>
          </div>
        </>
      )}
      <ErrorMessage error={error} />
    </div>
  );
}

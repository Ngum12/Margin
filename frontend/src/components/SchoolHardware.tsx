import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { ErrorMessage, Loading } from "./ui";
import { useLoad } from "./useLoad";

interface Hardware {
  inbox_enabled: boolean;
  inbox_path: string;
  printer_uri: string;
  duplex: boolean;
  last_scan_at: string | null;
  test_started_at: string | null;
  test_received: boolean;
  waiting_files: number;
  oversized_files: number;
}

export function SchoolHardware() {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => request<Hardware>("GET", "/api/hardware"), []);
  useEffect(() => {
    const timer = setInterval(reload, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  return <HardwareForm initial={state.data} reload={reload} title={t("hardware.title")} />;
}

function HardwareForm({
  initial,
  reload,
  title,
}: {
  initial: Hardware;
  reload: () => void;
  title: string;
}) {
  const { t } = useTranslation();
  const [uri, setUri] = useState(initial.printer_uri);
  const [enabled, setEnabled] = useState(initial.inbox_enabled);
  const [duplex, setDuplex] = useState(initial.duplex);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{title}</h2>
      <p>{t("hardware.help")}</p>
      <p>
        <strong>{t("hardware.folder")}</strong> <code>{initial.inbox_path}</code>
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void run(async () => {
            await request("PUT", "/api/hardware", {
              json: { inbox_enabled: enabled, printer_uri: uri, duplex },
            });
            setMessage(t("hardware.saved"));
          });
        }}
      >
        <label>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => {
              setEnabled(e.target.checked);
            }}
          />{" "}
          {t("hardware.enable")}
        </label>
        <label>
          {t("hardware.printer")}
          <input
            value={uri}
            placeholder="ipp://192.168.1.50:631/ipp/print"
            onChange={(e) => {
              setUri(e.target.value);
            }}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={duplex}
            onChange={(e) => {
              setDuplex(e.target.checked);
            }}
          />{" "}
          {t("hardware.duplex")}
        </label>
        <button disabled={busy} type="submit">
          {t("hardware.save")}
        </button>
      </form>
      <div className="button-row">
        <button
          className="button-secondary"
          disabled={busy || !initial.inbox_enabled}
          onClick={() => {
            void run(async () => {
              await request("POST", "/api/hardware/test-scan");
              setMessage(t("hardware.sendScan"));
            });
          }}
        >
          {t("hardware.testScan")}
        </button>
        <button
          className="button-secondary"
          disabled={busy || !initial.printer_uri}
          onClick={() => {
            void run(async () => {
              const result = await request<{ connected: boolean; error_code?: string }>(
                "POST",
                "/api/hardware/test-printer",
              );
              setMessage(
                result.connected
                  ? t("hardware.connected")
                  : t(`errors.${result.error_code ?? "hardware.printer_unreachable"}`),
              );
            });
          }}
        >
          {t("hardware.checkPrinter")}
        </button>
        <button
          className="button-secondary"
          disabled={busy || !initial.printer_uri}
          onClick={() => {
            void run(async () => {
              await request("POST", "/api/print-jobs", {
                json: { request_key: crypto.randomUUID(), kind: "test" },
              });
              setMessage(t("hardware.queued"));
            });
          }}
        >
          {t("hardware.testPrint")}
        </button>
      </div>
      {initial.test_started_at && (
        <p role="status">
          {t(initial.test_received ? "hardware.scanReceived" : "hardware.sendScan")}
        </p>
      )}
      {initial.oversized_files > 0 && <p role="alert">{t("hardware.oversized")}</p>}
      <p role="status">{message}</p>
      {error != null && <ErrorMessage error={error} />}
      <PrintQueue />
    </section>
  );
}

interface PrintJob {
  id: number;
  exam_id: number | null;
  status: string;
  error_code: string | null;
}
export function PrintQueue({ examId }: { examId?: number }) {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => request<PrintJob[]>("GET", "/api/print-jobs"), []);
  const [error, setError] = useState<unknown>(null);
  const [checked, setChecked] = useState<number[]>([]);
  useEffect(() => {
    const timer = setInterval(reload, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  if (state.status !== "ready" || state.data.length === 0) return null;
  return (
    <div>
      <h3>{t("hardware.queue")}</h3>
      {state.data
        .filter((j) => examId === undefined || j.exam_id === examId)
        .map((job) => (
          <div className="panel" key={job.id}>
            <strong>
              #{job.id} · {t(`hardware.status.${job.status}`)}
            </strong>
            {job.error_code && <p>{t(`errors.${job.error_code}`)}</p>}
            {job.status === "unknown" && (
              <label>
                <input
                  type="checkbox"
                  checked={checked.includes(job.id)}
                  onChange={(e) => {
                    setChecked(
                      e.target.checked
                        ? [...checked, job.id]
                        : checked.filter((id) => id !== job.id),
                    );
                  }}
                />
                {t("hardware.checkedPrinter")}
              </label>
            )}
            {["failed", "unknown"].includes(job.status) && (
              <button
                disabled={job.status === "unknown" && !checked.includes(job.id)}
                onClick={() => {
                  void request("POST", `/api/print-jobs/${String(job.id)}/retry`, {
                    json: { acknowledge_uncertain: checked.includes(job.id) },
                  })
                    .then(reload)
                    .catch(setError);
                }}
              >
                {t("hardware.retry")}
              </button>
            )}
          </div>
        ))}
      {error != null && <ErrorMessage error={error} />}
    </div>
  );
}

export function PrintControls({
  examId,
  scriptId,
  students = [],
}: {
  examId: number;
  scriptId?: number;
  students?: { id: number; name: string }[];
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [kind, setKind] = useState("feedback");
  const [selected, setSelected] = useState<number[]>([]);
  async function print(unprinted: boolean, selection = false) {
    setBusy(true);
    setError(null);
    try {
      await request("POST", "/api/print-jobs", {
        json: {
          exam_id: examId,
          ...(scriptId ? { script_ids: [scriptId] } : selection ? { script_ids: selected } : {}),
          request_key: crypto.randomUUID(),
          kind,
          unprinted,
        },
      });
      setSent(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h3>{t("hardware.return")}</h3>
      <label>
        {t("hardware.method")}
        <select
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
          }}
        >
          <option value="feedback">{t("hardware.feedback")}</option>
          <option value="full">{t("hardware.full")}</option>
        </select>
      </label>
      <button
        disabled={busy}
        onClick={() => {
          void print(false);
        }}
      >
        {t(scriptId ? "hardware.print" : "hardware.printAll")}
      </button>
      {!scriptId && (
        <button
          className="button-secondary"
          disabled={busy}
          onClick={() => {
            void print(true);
          }}
        >
          {t("hardware.printUnprinted")}
        </button>
      )}
      {!scriptId && students.length > 0 && (
        <details>
          <summary>{t("hardware.selectStudents")}</summary>
          {students.map((student) => (
            <label key={student.id}>
              <input
                type="checkbox"
                checked={selected.includes(student.id)}
                onChange={(e) => {
                  setSelected(
                    e.target.checked
                      ? [...selected, student.id]
                      : selected.filter((id) => id !== student.id),
                  );
                }}
              />{" "}
              {student.name}
            </label>
          ))}
          <button
            disabled={busy || selected.length === 0}
            onClick={() => {
              void print(false, true);
            }}
          >
            {t("hardware.printSelected")}
          </button>
        </details>
      )}
      {scriptId && (
        <a className="button-secondary" href={`/api/scripts/${String(scriptId)}/feedback.pdf`}>
          {t("hardware.downloadSlip")}
        </a>
      )}
      {sent && <p role="status">{t("hardware.queued")}</p>}
      {error != null && <ErrorMessage error={error} />}
      <PrintQueue examId={examId} />
    </section>
  );
}

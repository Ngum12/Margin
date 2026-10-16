import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { useLoad } from "./useLoad";
import { ErrorMessage } from "./ui";

interface Intake {
  batches: { id: number; status: string }[];
  pages: { id: number; page: number; reason: string; exam_id: number | null }[];
  quarantine: { id: number; error_code: string }[];
}
interface ExamChoice {
  id: number;
  title: string;
  class_id: number;
}
interface StudentChoice {
  id: number;
  code: string;
  display_name: string | null;
}

export function ScanInbox() {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => request<Intake>("GET", "/api/intake"), []);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const timer = setInterval(reload, 10000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  if (
    state.status !== "ready" ||
    (!state.data.pages.length && !state.data.quarantine.length && !state.data.batches.length)
  )
    return null;
  return (
    <section className="panel">
      <button
        className="button-secondary"
        onClick={() => {
          setOpen(!open);
        }}
        aria-expanded={open}
      >
        {t("hardware.attention", { count: state.data.pages.length + state.data.quarantine.length })}
      </button>
      {open && (
        <>
          <p>{t("hardware.attentionHelp")}</p>
          {state.data.batches.map((batch) => (
            <p key={batch.id}>
              #{batch.id}{" "}
              <button
                className="button-secondary"
                onClick={() => {
                  void request("DELETE", `/api/scan-batches/${String(batch.id)}`)
                    .then(reload)
                    .catch(setError);
                }}
              >
                {t("hardware.removeBatch")}
              </button>
            </p>
          ))}
          {error != null && <ErrorMessage error={error} />}
          {state.data.pages.map((page) => (
            <MatchPage key={page.id} page={page} reload={reload} />
          ))}
          {state.data.quarantine.map((batch) => (
            <p key={batch.id}>
              #{batch.id}: {t(`errors.${batch.error_code}`)}
            </p>
          ))}
        </>
      )}
    </section>
  );
}

function MatchPage({ page, reload }: { page: Intake["pages"][number]; reload: () => void }) {
  const { t } = useTranslation();
  const [examId, setExamId] = useState(page.exam_id ?? 0);
  const [studentId, setStudentId] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const exams = useLoad(() => request<ExamChoice[]>("GET", "/api/exams"), []);
  const schoolClass =
    exams.state.status === "ready"
      ? exams.state.data.find((e) => e.id === examId)?.class_id
      : undefined;
  const students = useLoad(
    () =>
      schoolClass
        ? request<StudentChoice[]>("GET", `/api/classes/${String(schoolClass)}/students`)
        : Promise.resolve([]),
    [schoolClass],
  );
  return (
    <article className="panel">
      <a href={`/api/intake/${String(page.id)}/image`} target="_blank" rel="noreferrer">
        {t("hardware.openPage", { page: page.page })}
      </a>
      <p>{t(`hardware.reason.${page.reason}`)}</p>
      <label>
        {t("hardware.exam")}
        <select
          value={examId}
          onChange={(e) => {
            setExamId(Number(e.target.value));
            setStudentId(0);
          }}
        >
          <option value="0">—</option>
          {exams.state.status === "ready" &&
            exams.state.data.map((exam) => (
              <option value={exam.id} key={exam.id}>
                {exam.title}
              </option>
            ))}
        </select>
      </label>
      <label>
        {t("hardware.student")}
        <select
          value={studentId}
          onChange={(e) => {
            setStudentId(Number(e.target.value));
          }}
        >
          <option value="0">—</option>
          {students.state.status === "ready" &&
            students.state.data.map((student) => (
              <option value={student.id} key={student.id}>
                {student.display_name ?? student.code}
              </option>
            ))}
        </select>
      </label>
      <button
        disabled={!examId || !studentId}
        onClick={() => {
          void request("POST", `/api/intake/${String(page.id)}/assign`, {
            json: { exam_id: examId, student_id: studentId },
          })
            .then(reload)
            .catch(setError);
        }}
      >
        {t("hardware.match")}
      </button>
      <button
        className="button-secondary"
        onClick={() => {
          void request("POST", `/api/intake/${String(page.id)}/discard`)
            .then(reload)
            .catch(setError);
        }}
      >
        {t("hardware.discardPage")}
      </button>
      {error != null && <ErrorMessage error={error} />}
    </article>
  );
}

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { studentRequest } from "../api/student";
import type { Overlay, Remark, StudentExam, StudentMe } from "../api/student";
import { ErrorMessage, Loading } from "../components/ui";
import { ApiError } from "../api/client";

export default function StudentPortal() {
  const { t } = useTranslation();
  const [me, setMe] = useState<StudentMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [exams, setExams] = useState<StudentExam[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  function loadExams() {
    void studentRequest<StudentExam[]>("exams").then(setExams).catch(setError);
  }
  useEffect(() => {
    let alive = true;
    void studentRequest<StudentMe>("me")
      .then((value) => {
        if (alive) setMe(value);
      })
      .catch((err: unknown) => {
        if (alive && (!(err instanceof ApiError) || err.status !== 401)) setError(err);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (me && !me.must_change_pin) loadExams();
  }, [me]);
  // Clear private state on inactivity and when the browser restores a cached page.
  useEffect(() => {
    if (!me) return;
    let timer: ReturnType<typeof setTimeout>;
    const clear = () => {
      setMe(null);
      setExams([]);
      setSelected(null);
      void studentRequest("logout", "POST").catch(() => undefined);
    };
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(clear, (me.idle_minutes ?? 2) * 60 * 1000);
    };
    const restored = (e: PageTransitionEvent) => {
      if (e.persisted) clear();
    };
    reset();
    window.addEventListener("pointerdown", reset);
    window.addEventListener("keydown", reset);
    window.addEventListener("pageshow", restored);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("pointerdown", reset);
      window.removeEventListener("keydown", reset);
      window.removeEventListener("pageshow", restored);
    };
  }, [me]);
  const exam = exams.find((e) => e.id === selected);
  if (loading) return <Loading />;
  return (
    <section className="student-portal">
      <header className="page-header">
        <div>
          <p className="eyebrow">{t("portal.title")}</p>
          <h1>{me ? (me.name ?? me.code) : t("portal.signin")}</h1>
        </div>
        {me && (
          <button
            onClick={() => {
              void studentRequest("logout", "POST")
                .then(() => {
                  setMe(null);
                  setExams([]);
                  setSelected(null);
                })
                .catch(setError);
            }}
          >
            {t("portal.signout")}
          </button>
        )}
      </header>
      <ErrorMessage error={error} />
      {!me ? (
        <StudentLogin onLogin={setMe} />
      ) : me.must_change_pin ? (
        <PinChange onChanged={setMe} />
      ) : (
        <>
          {exam ? (
            <>
              <button
                onClick={() => {
                  setSelected(null);
                }}
              >
                {t("portal.back")}
              </button>
              <ExamWork key={exam.id} exam={exam} reload={loadExams} />
            </>
          ) : (
            <>
              <h2>{t("portal.myExams")}</h2>
              {exams.length === 0 && <p>{t("portal.noExams")}</p>}
              <div className="student-exams">
                {exams.map((e) => (
                  <button
                    className="panel student-exam"
                    key={e.id}
                    onClick={() => {
                      setSelected(e.id);
                    }}
                  >
                    <span>
                      {e.subject} · {e.term} · {e.date}
                    </span>
                    <strong>{e.title}</strong>
                    <span>
                      {e.total} / {e.maximum}
                    </span>
                    {e.remarks.some((r) => r.unread) && (
                      <span className="badge">{t("portal.newReply")}</span>
                    )}
                  </button>
                ))}
              </div>
              <h2>{t("portal.progress")}</h2>
              {[...new Set(exams.map((e) => e.subject))].map((subject) => (
                <div className="panel" key={subject}>
                  <h3>{subject}</h3>
                  <ol>
                    {exams
                      .filter((e) => e.subject === subject)
                      .slice()
                      .reverse()
                      .map((e) => (
                        <li key={e.id}>
                          {e.date} · {e.title}: {e.total}/{e.maximum}{" "}
                          <meter
                            min={0}
                            max={e.maximum || 1}
                            value={e.total}
                            aria-label={e.title}
                          />
                        </li>
                      ))}
                  </ol>
                  <h4>{t("portal.revise")}</h4>
                  <ul>
                    {exams
                      .filter((e) => e.subject === subject)
                      .flatMap((e) =>
                        e.questions
                          .filter((q) => q.marks < q.maximum)
                          .map((q) => (
                            <li key={`${String(e.id)}-${String(q.id)}`}>
                              {e.title} — {q.label}: {q.prompt || t("portal.reviewQuestion")}
                            </li>
                          )),
                      )
                      .slice(0, 8)}
                  </ul>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </section>
  );
}

function StudentLogin({ onLogin }: { onLogin: (me: StudentMe) => void }) {
  const { t } = useTranslation();
  const [schools, setSchools] = useState<{ id: number; name: string }[]>([]);
  const [school, setSchool] = useState(0);
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void studentRequest<{ id: number; name: string }[]>("schools")
      .then((rows) => {
        setSchools(rows);
        setSchool(rows[0]?.id ?? 0);
      })
      .catch(setError);
  }, []);
  return (
    <form
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        void studentRequest<StudentMe>("login", "POST", { school_id: school, code, pin })
          .then(onLogin)
          .catch(setError)
          .finally(() => {
            setPin("");
            setBusy(false);
          });
      }}
    >
      <p>{t("portal.signinHint")}</p>
      <ErrorMessage error={error} />
      <label>
        {t("portal.school")}
        <select
          value={school}
          onChange={(e) => {
            setSchool(Number(e.target.value));
          }}
        >
          {schools.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("portal.code")}
        <input
          value={code}
          maxLength={16}
          autoComplete="username"
          required
          onChange={(e) => {
            setCode(e.target.value);
          }}
        />
      </label>
      <label>
        {t("portal.pin")}
        <input
          type="password"
          inputMode="numeric"
          autoComplete="current-password"
          value={pin}
          required
          maxLength={12}
          onChange={(e) => {
            setPin(e.target.value);
          }}
        />
      </label>
      <button className="primary" disabled={busy || !school}>
        {t("portal.signin")}
      </button>
      {schools.length === 0 && <p>{t("portal.disabled")}</p>}
    </form>
  );
}

function PinChange({ onChanged }: { onChanged: (me: StudentMe) => void }) {
  const { t } = useTranslation();
  const [old, setOld] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<unknown>(null);
  return (
    <form
      className="panel"
      onSubmit={(e) => {
        e.preventDefault();
        void studentRequest<StudentMe>("pin", "PUT", { old_pin: old, pin })
          .then(onChanged)
          .catch(setError);
      }}
    >
      <h2>{t("portal.changePin")}</h2>
      <ErrorMessage error={error} />
      <label>
        {t("portal.oldPin")}
        <input
          type="password"
          inputMode="numeric"
          value={old}
          required
          onChange={(e) => {
            setOld(e.target.value);
          }}
        />
      </label>
      <label>
        {t("portal.newPin")}
        <input
          type="password"
          inputMode="numeric"
          pattern="[0-9]{6,12}"
          minLength={6}
          maxLength={12}
          value={pin}
          required
          onChange={(e) => {
            setPin(e.target.value);
          }}
        />
      </label>
      <button>{t("common.save")}</button>
    </form>
  );
}

function ExamWork({ exam, reload }: { exam: StudentExam; reload: () => void }) {
  const { t } = useTranslation();
  const [marks, setMarks] = useState<Overlay>({ pages: [] });
  const [show, setShow] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    void studentRequest<Overlay>(`scripts/${String(exam.id)}/marks`)
      .then(setMarks)
      .catch(setError);
  }, [exam.id]);
  return (
    <article>
      <h2>
        {exam.title} · {exam.total}/{exam.maximum}
      </h2>
      {exam.class_average != null && (
        <p>{t("portal.average", { marks: exam.class_average.toFixed(1) })}</p>
      )}

      <ErrorMessage error={error} />
      <label>
        <input
          type="checkbox"
          checked={show}
          onChange={(e) => {
            setShow(e.target.checked);
          }}
        />
        {t("portal.overlay")}
      </label>
      <label>
        {t("portal.zoom")}
        <input
          type="range"
          min="1"
          max="3"
          step="0.25"
          value={zoom}
          onChange={(e) => {
            setZoom(Number(e.target.value));
          }}
        />
      </label>
      <div className="student-pages">
        {exam.pages.map((p) => (
          <div className="student-page-scroll" key={p.id}>
            <div className="student-page" style={{ width: `${String(zoom * 100)}%` }}>
              <img
                src={`/api/student/pages/${String(p.id)}/image`}
                alt={t("portal.page", { number: p.position })}
              />
              {show &&
                marks.pages
                  .find((m) => m.page_id === p.id)
                  ?.marks.map((m, i) => (
                    <span
                      key={i}
                      className="student-mark"
                      style={{
                        left: `${String(m.x * 100)}%`,
                        top: `${String(m.y * 100)}%`,
                        fontSize: `${String(Math.max(m.size * 100, 1))}cqw`,
                      }}
                    >
                      {m.kind === "tick"
                        ? "✓"
                        : m.kind === "cross"
                          ? "×"
                          : m.kind === "partial"
                            ? `½ ${m.text}`
                            : m.text}
                    </span>
                  ))}
            </div>
          </div>
        ))}
      </div>
      {exam.questions.map((q) => (
        <section className="panel" key={q.id}>
          <h3>
            {q.label}: {q.marks}/{q.maximum}
          </h3>
          <p>{q.prompt}</p>
          {q.comment && <p>{q.comment}</p>}
          {q.feedback.map((f, i) => (
            <p key={i}>
              {t(`category.${f.category}`)} · {f.evidence}{" "}
              {f.pages
                .map((id) =>
                  t("portal.page", {
                    number: exam.pages.find((p) => p.id === id)?.position ?? "?",
                  }),
                )
                .join(", ")}
            </p>
          ))}
          {q.scheme.length > 0 && (
            <details>
              <summary>{t("portal.scheme")}</summary>
              <ul>
                {q.scheme.map((p, i) => (
                  <li key={i}>
                    {p.description} ({p.marks}) {p.alternatives.join(" / ")}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {exam.remarks.some((r) => r.question_id === q.id) ? (
            exam.remarks
              .filter((r) => r.question_id === q.id)
              .map((r) => (
                <RemarkThread key={r.id} remark={r} escalation={exam.escalation} reload={reload} />
              ))
          ) : (
            <RemarkForm exam={exam} questionId={q.id} reload={reload} />
          )}
        </section>
      ))}
    </article>
  );
}

function RemarkForm({
  exam,
  questionId,
  reload,
}: {
  exam: StudentExam;
  questionId: number;
  reload: () => void;
}) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("missing_mark");
  const [message, setMessage] = useState("");
  const [page, setPage] = useState("");
  const [location, setLocation] = useState<{ x: number; y: number } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [openedAt] = useState(() => Date.now());
  const closed =
    openedAt > new Date(exam.released_at).getTime() + exam.remark_days * 86400000 ||
    exam.remarks.length >= exam.remark_max;
  if (closed) return <p>{t("portal.remarkUnavailable")}</p>;
  return (
    <details>
      <summary>{t("portal.askRemark")}</summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void studentRequest(`scripts/${String(exam.id)}/remarks`, "POST", {
            question_id: questionId,
            reason,
            message,
            page_id: page ? Number(page) : null,
            ...(location ?? {}),
          })
            .then(reload)
            .catch(setError);
        }}
      >
        <ErrorMessage error={error} />
        <label>
          {t("portal.reason")}
          <select
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
            }}
          >
            {["missing_mark", "total_error", "unmarked_answer", "other"].map((r) => (
              <option value={r} key={r}>
                {t(`portal.reasons.${r}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("portal.pageChoice")}
          <select
            value={page}
            onChange={(e) => {
              setPage(e.target.value);
              setLocation(null);
            }}
          >
            <option value="">—</option>
            {exam.pages.map((p) => (
              <option key={p.id} value={p.id}>
                {t("portal.page", { number: p.position })}
              </option>
            ))}
          </select>
        </label>
        {page && (
          <button
            type="button"
            className="remark-page"
            aria-label={t("portal.pointOnPage")}
            onClick={(e) => {
              const box = e.currentTarget.getBoundingClientRect();
              setLocation({
                x: e.detail ? Math.max(0, Math.min(1, (e.clientX - box.left) / box.width)) : 0.5,
                y: e.detail ? Math.max(0, Math.min(1, (e.clientY - box.top) / box.height)) : 0.5,
              });
            }}
          >
            <img src={`/api/student/pages/${page}/image`} alt={t("portal.pointOnPage")} />
            {location && (
              <span
                className="remark-pin"
                style={{
                  left: `${String(location.x * 100)}%`,
                  top: `${String(location.y * 100)}%`,
                }}
              >
                ◎
              </span>
            )}
          </button>
        )}
        <label>
          {t("portal.message")}
          <textarea
            required
            maxLength={500}
            value={message}
            onChange={(e) => {
              setMessage(e.target.value);
            }}
          />
        </label>
        <button>{t("portal.send")}</button>
      </form>
    </details>
  );
}

function RemarkThread({
  remark: r,
  escalation,
  reload,
}: {
  remark: Remark;
  escalation: boolean;
  reload: () => void;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<unknown>(null);
  return (
    <div className="remark-thread">
      <p>
        <strong>{t(`portal.status.${r.status}`)}</strong> · {r.message}
      </p>
      <ErrorMessage error={error} />
      {r.responses.map((reply, i) => (
        <p key={i}>
          {reply.automatic ? t("portal.totalCorrect", { total: reply.total }) : reply.message}
          {reply.changed && ` (${String(reply.old_marks)} → ${String(reply.new_marks)})`}
        </p>
      ))}
      {r.unread && (
        <button
          onClick={() => {
            void studentRequest(`remarks/${String(r.id)}/seen`, "POST")
              .then(reload)
              .catch(setError);
          }}
        >
          {t("portal.markRead")}
        </button>
      )}
      {escalation && r.status === "answered" && !r.escalated_once && (
        <button
          onClick={() => {
            void studentRequest(`remarks/${String(r.id)}/escalate`, "POST")
              .then(reload)
              .catch(setError);
          }}
        >
          {t("portal.escalate")}
        </button>
      )}
    </div>
  );
}

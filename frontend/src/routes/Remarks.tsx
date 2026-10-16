import type { ScriptReview } from "../api/types";
import { useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import type { Remark } from "../api/student";
import { useLoad } from "../components/useLoad";
import { ErrorMessage, Loading } from "../components/ui";

export default function Remarks() {
  const { t } = useTranslation();
  const { state } = useLoad(() => request<Remark[]>("GET", "/api/remarks"), []);
  return (
    <section>
      <h1>{t("portal.remarks")}</h1>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorMessage error={state.error} />}{" "}
      {state.status === "ready" && (
        <>
          <p>
            {t("portal.remarkStats", {
              count: state.data.length,
              changed: state.data.filter((r) => r.responses.some((reply) => reply.changed)).length,
            })}
          </p>
          <ul>
            {[...new Set(state.data.map((r) => r.exam_id))].map((id) => {
              const rows = state.data.filter((r) => r.exam_id === id);
              return (
                <li key={id}>
                  <Link to={`/exams/${String(id)}/results`}>
                    {t("portal.examNumber", { number: id })}
                  </Link>
                  :{" "}
                  {t("portal.remarkStats", {
                    count: rows.length,
                    changed: rows.filter((r) => r.responses.some((reply) => reply.changed)).length,
                  })}
                </li>
              );
            })}
          </ul>
          {state.data.map((r) => (
            <article className="panel" key={r.id}>
              <h2>
                {t(`portal.status.${r.status}`)} · {t(`portal.reasons.${r.reason}`)}
              </h2>
              <p>{r.message}</p>
              <Link
                to={`/exams/${String(r.exam_id)}/review/${String(r.script_id)}?remark=${String(r.id)}&question=${String(r.question_id)}${r.page_id ? `&page=${String(r.page_id)}` : ""}`}
              >
                {t("portal.openReview")}
              </Link>
            </article>
          ))}
        </>
      )}
    </section>
  );
}

export function RemarkDesk({ review }: { review: ScriptReview }) {
  const { state, reload } = useLoad(
    () => request<Remark[]>("GET", "/api/remarks"),
    [review.script.id],
  );
  if (state.status !== "ready") return null;
  return (
    <>
      {state.data
        .filter((r) => r.script_id === review.script.id && r.status !== "answered")
        .map((r) => (
          <ReplyForm key={r.id} remark={r} review={review} reload={reload} />
        ))}
    </>
  );
}
function ReplyForm({
  remark: r,
  review,
  reload,
}: {
  remark: Remark;
  review: ScriptReview;
  reload: () => void;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState("");
  const [marks, setMarks] = useState<Record<number, number>>({});
  const question = review.questions.find((q) => q.id === r.question_id);
  return (
    <section className="panel remark-desk">
      <h3>
        {t("portal.remarks")} · {question?.label}
      </h3>
      <p>{r.message}</p>
      <p>{t("portal.replyHint")}</p>
      <ErrorMessage error={error} />
      <button
        onClick={() => {
          void request("POST", `/api/remarks/${String(r.id)}/open`)
            .then(reload)
            .catch(setError);
        }}
      >
        {t("portal.startLooking")}
      </button>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void request("POST", `/api/remarks/${String(r.id)}/reply`, { json: { message, marks } })
            .then(() => {
              window.location.reload();
            })
            .catch(setError);
        }}
      >
        <label>
          {t("portal.reply")}
          <textarea
            value={message}
            maxLength={500}
            required
            onChange={(e) => {
              setMessage(e.target.value);
            }}
          />
        </label>
        {question?.points.map((p) => (
          <label key={p.id}>
            {p.description}
            <input
              type="number"
              min={0}
              max={p.max_marks}
              step={1}
              value={marks[p.id] ?? p.final_marks ?? ""}
              onChange={(e) => {
                setMarks({ ...marks, [p.id]: Number(e.target.value) });
              }}
            />
          </label>
        ))}
        <button>{t("portal.sendReply")}</button>
      </form>
    </section>
  );
}

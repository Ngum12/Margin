import { PrintControls } from "../components/SchoolHardware";
import { useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { api } from "../api/endpoints";
import type {
  ErrorCategory,
  RedPen,
  ReviewPage,
  ReviewPoint,
  ReviewQuestion,
  ScriptReview,
} from "../api/types";
import { ERROR_CATEGORIES } from "../api/types";
import { useBreadcrumb } from "../components/breadcrumb";
import { Icon } from "../components/Icon";
import { ErrorMessage, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { evidenceLines, formatLines, highlight } from "../review/evidence";
import { flatPoints, nextDeduction, step } from "../review/focus";
import type { FlatPoint } from "../review/focus";
import { actionForKey, activatesOnEnter, isTypingTarget, SHORTCUTS } from "../review/keyboard";
import type { ReviewAction } from "../review/keyboard";
import { ConfirmButton, ModelLabel, TestModelBanner } from "../review/ModelLabel";
import { PageViewer } from "../review/PageViewer";
import { useHeartbeat } from "../review/useHeartbeat";
import { FIT, nextCategory, rotate, zoomIn, zoomOut } from "../review/viewer";

/** The marking desk: the scanned page on the left, the current question's mark scheme as a
 * checklist on the right. Everything can be done from the keyboard (`?` lists the keys). */
export default function Review() {
  const params = useParams();
  const examId = Number(params.examId);
  const scriptId = Number(params.scriptId);
  const { state, set } = useLoad(() => api.review(scriptId), [scriptId]);

  if (state.status === "error") return <ErrorMessage error={state.error} />;
  if (state.status === "loading") return <Loading />;
  return <ReviewScreen key={scriptId} examId={examId} review={state.data} onChange={set} />;
}

function firstAnswerPage(pages: ReviewPage[]): number {
  const index = pages.findIndex((p) => !p.is_cover);
  return index < 0 ? 0 : index;
}

/** Where the AI's evidence for a point is: the page and its line numbers. */
function evidenceLocation(pages: ReviewPage[], evidence: string) {
  if (!evidence) return null;
  for (const [index, page] of pages.entries()) {
    if (!page.transcription) continue;
    const lines = evidenceLines(page.transcription.text, evidence);
    if (lines.length > 0) return { pageIndex: index, lines };
  }
  return null;
}

type Tone = "info" | "confirmed";

function ReviewScreen({
  examId,
  review,
  onChange,
}: {
  examId: number;
  review: ScriptReview;
  onChange: (review: ScriptReview) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const scriptId = review.script.id;
  const points = useMemo(() => flatPoints(review.questions), [review.questions]);
  const [focus, setFocus] = useState(0);
  const [pageIndex, setPageIndex] = useState(() => firstAnswerPage(review.pages));
  const [view, setView] = useState(FIT);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [help, setHelp] = useState(false);
  const [redPenOn, setRedPenOn] = useState(readRedPenSetting);
  const [showEvidence, setShowEvidence] = useState(true);
  const [redPen, setRedPen] = useState<RedPen | null>(null);
  // The confirmed total settles with a short stamp, only when the teacher confirms it here.
  const [stamped, setStamped] = useState(false);
  // Saves waiting to finish. Keys are never dropped: every change joins an ordered queue.
  const [pending, setPending] = useState(0);
  const busy = pending > 0;
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<{ text: string; tone: Tone } | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const comments = useRef(new Map<number, HTMLInputElement>());
  const pointItems = useRef(new Map<number, HTMLLIElement>());

  const editable = review.ready && !review.locked;
  useHeartbeat(scriptId, editable);
  useBreadcrumb([
    { label: review.exam.title, to: `/exams/${String(examId)}/queue` },
    { label: review.script.student_name ?? review.script.student_code },
  ]);

  const page = review.pages[pageIndex];
  const current: FlatPoint | undefined = points[focus];
  const currentQuestion = current?.question ?? review.questions[0];

  function say(text: string, tone: Tone = "info") {
    setNotice({ text, tone });
  }

  // When the focus moves to another point, keep it in view and show the page its evidence is on.
  const focusedId = current?.point.id;
  const focusedEvidence = current?.point.evidence ?? "";
  const pagesRef = useRef(review.pages);
  const editingRef = useRef(editing);
  // Opening a script shows its top (student, total); only later focus moves scroll.
  const firstFocus = useRef(true);
  useEffect(() => {
    pagesRef.current = review.pages;
    editingRef.current = editing;
  });
  useEffect(() => {
    if (focusedId === undefined) return;
    if (firstFocus.current) firstFocus.current = false;
    else pointItems.current.get(focusedId)?.scrollIntoView({ block: "nearest" });
    if (editingRef.current || !focusedEvidence) return;
    const onPage = pagesRef.current.findIndex(
      (p) =>
        p.transcription !== null &&
        highlight(p.transcription.text, focusedEvidence).some((s) => s.mark),
    );
    if (onPage >= 0) setPageIndex(onPage);
  }, [focusedId, focusedEvidence]);

  useEffect(() => {
    if (editing) textarea.current?.focus();
  }, [editing]);

  // The red pen layout also tells where each point's evidence lines are on the page.
  useEffect(() => {
    let cancelled = false;
    api
      .redPen(scriptId)
      .then((layout) => {
        if (!cancelled) setRedPen(layout);
      })
      .catch(() => {
        // The red pen is a preview; the review works without it.
      });
    return () => {
      cancelled = true;
    };
  }, [review, scriptId]);

  function switchRedPen(on: boolean) {
    setRedPenOn(on);
    try {
      window.localStorage.setItem(RED_PEN_KEY, on ? "on" : "off");
    } catch {
      // Remembering the choice is a convenience only.
    }
  }

  function suggestComment(question: ReviewQuestion) {
    const missed = question.points.filter((p) => {
      const marks = p.final_marks ?? p.proposed_marks;
      return marks !== null && marks < p.max_marks;
    });
    if (missed.length === 0) return;
    const hint = `${t("redPen.suggestPrefix")} ${missed.map((p) => p.description).join("; ")}`;
    const text = [question.comment, hint].filter(Boolean).join(" ").slice(0, 300);
    run(() => api.setComment(scriptId, question.id, text));
  }

  // Changes run one after another, in the order the teacher made them. Each one is worked out
  // from the latest saved review when its turn comes, so quick key presses are never lost or
  // based on out-of-date marks.
  const latest = useRef(review);
  const chain = useRef<Promise<void>>(Promise.resolve());
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  type Step = (
    current: ScriptReview,
  ) => Promise<{ review: ScriptReview; notice?: string | undefined; tone?: Tone } | null>;

  function enqueue(work: Step) {
    setPending((n) => n + 1);
    setError(null);
    setNotice(null);
    chain.current = chain.current.then(async () => {
      try {
        const result = await work(latest.current);
        if (result && alive.current) {
          latest.current = result.review;
          onChange(result.review);
          if (result.notice) say(result.notice, result.tone);
        }
      } catch (err) {
        if (alive.current) setError(err);
      } finally {
        if (alive.current) setPending((n) => n - 1);
      }
    });
  }

  function run(call: () => Promise<ScriptReview>, message?: string) {
    enqueue(async () => ({ review: await call(), notice: message }));
  }

  function findPoint(current: ScriptReview, pointId: number) {
    return current.questions.flatMap((q) => q.points).find((p) => p.id === pointId);
  }

  function goToPage(index: number) {
    if (index < 0 || index >= review.pages.length) return;
    setPageIndex(index);
    setView(FIT);
    setEditing(false);
  }

  function goToQuestion(questionId: number) {
    const index = points.findIndex((p) => p.question.id === questionId);
    if (index >= 0) setFocus(index);
  }

  function stepQuestion(delta: 1 | -1) {
    const index = review.questions.findIndex((q) => q.id === currentQuestion?.id);
    const target = review.questions[index + delta];
    if (target) goToQuestion(target.id);
  }

  function setMarks(item: FlatPoint, marks: number) {
    if (marks > item.point.max_marks) {
      say(t("review.marksTooHigh", { max: item.point.max_marks }));
      return;
    }
    run(() => api.setDecision(scriptId, item.point.id, { marks }));
  }

  function setCategory(item: FlatPoint, category: ErrorCategory) {
    run(() => api.setDecision(scriptId, item.point.id, { category }));
  }

  function cycleCategory(item: FlatPoint) {
    const pointId = item.point.id;
    enqueue(async (current) => {
      const point = findPoint(current, pointId);
      if (!point) return null;
      const category = nextCategory(point.final_category, point.error_category);
      return { review: await api.setDecision(scriptId, pointId, { category }) };
    });
  }

  function accept(item: FlatPoint) {
    if (item.point.proposed_marks === null) {
      say(t("review.noProposal"));
      return;
    }
    run(() => api.acceptPoint(scriptId, item.point.id));
  }

  function acceptAll() {
    enqueue(async () => {
      const result = await api.acceptAll(scriptId);
      return {
        review: result.review,
        notice: t("review.acceptedAll", { count: result.accepted }),
      };
    });
  }

  function confirm() {
    enqueue(async (current) => {
      if (!current.can_confirm) {
        say(t("review.cannotConfirm"));
        return null;
      }
      const confirmed = await api.confirmScript(scriptId);
      setStamped(true);
      return { review: confirmed, notice: t("review.confirmed"), tone: "confirmed" };
    });
  }

  function reopen() {
    setStamped(false);
    run(() => api.reopenScript(scriptId), t("review.reopened"));
  }

  function rotateBy(pageId: number, delta: 90 | -90) {
    enqueue(async (current) => {
      const target = current.pages.find((p) => p.id === pageId);
      if (!target) return null;
      return { review: await api.rotatePage(pageId, rotate(target.rotation, delta)) };
    });
  }

  function startEditing() {
    if (!page || page.is_cover || !editable) return;
    setDraft(page.transcription?.text ?? "");
    setEditing(true);
  }

  function saveTranscription() {
    if (!page) return;
    const pageId = page.id;
    setEditing(false);
    run(() => api.editTranscription(pageId, draft), t("review.transcriptionSaved"));
  }

  function goToScript(id: number | null) {
    if (id !== null) void navigate(`/exams/${String(examId)}/review/${String(id)}`);
  }

  function handle(action: ReviewAction) {
    const needsEdit = [
      "setMarks",
      "accept",
      "acceptAll",
      "cycleCategory",
      "rotateLeft",
      "rotateRight",
      "confirm",
    ];
    if (needsEdit.includes(action.type) && !editable) {
      say(review.locked ? t("review.lockedNotice") : t("review.notReady"));
      return;
    }
    switch (action.type) {
      case "nextPoint":
      case "prevPoint":
        setFocus((f) => step(f, action.type === "nextPoint" ? 1 : -1, points.length));
        return;
      case "nextQuestion":
      case "prevQuestion":
        stepQuestion(action.type === "nextQuestion" ? 1 : -1);
        return;
      case "nextDeduction": {
        const next = nextDeduction(points, focus);
        if (next === null) say(t("review.noDeductions"));
        else setFocus(next);
        return;
      }
      case "setMarks":
        if (current) setMarks(current, action.marks);
        return;
      case "accept":
        if (current) accept(current);
        return;
      case "acceptAll":
        acceptAll();
        return;
      case "cycleCategory":
        if (current) cycleCategory(current);
        return;
      case "focusComment":
        if (currentQuestion) comments.current.get(currentQuestion.id)?.focus();
        return;
      case "toggleEvidence":
        setShowEvidence((on) => !on);
        return;
      case "editTranscription":
        startEditing();
        return;
      case "prevPage":
        goToPage(pageIndex - 1);
        return;
      case "nextPage":
        goToPage(pageIndex + 1);
        return;
      case "zoomIn":
        setView((v) => zoomIn(v));
        return;
      case "zoomOut":
        setView((v) => zoomOut(v));
        return;
      case "zoomFit":
        setView(FIT);
        return;
      case "rotateLeft":
      case "rotateRight":
        if (page) rotateBy(page.id, action.type === "rotateRight" ? 90 : -90);
        return;
      case "nextScript":
        goToScript(review.navigation.next_id);
        return;
      case "prevScript":
        goToScript(review.navigation.previous_id);
        return;
      case "confirm":
        confirm();
        return;
      case "help":
        setHelp((h) => !h);
        return;
    }
  }

  // One window listener; it always calls the latest handler.
  const handler = useRef(handle);
  useEffect(() => {
    handler.current = handle;
  });
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setHelp(false);
        return;
      }
      if (isTypingTarget(event.target)) return;
      // Plain Enter on a focused button or link presses it; it does not confirm the script.
      if (
        event.key === "Enter" &&
        !event.ctrlKey &&
        !event.metaKey &&
        activatesOnEnter(event.target)
      )
        return;
      const action = actionForKey(event);
      if (!action) return;
      event.preventDefault();
      handler.current(action);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const name = review.script.student_name ?? review.script.student_code;
  const confirmed = review.script.status === "confirmed";
  const pageMarks = redPen?.pages.find((p) => p.page_id === page?.id && p.placed)?.marks;
  const evidenceBands =
    showEvidence && current
      ? (pageMarks ?? []).filter(
          (m) => m.point_id === current.point.id && ["tick", "cross", "partial"].includes(m.kind),
        )
      : [];
  const location = current ? evidenceLocation(review.pages, current.point.evidence) : null;
  const highlightLines =
    showEvidence && location && location.pageIndex === pageIndex ? location.lines : [];
  const finalTotal = review.totals.final_total;
  const scoreClass = [
    "desk-score",
    confirmed ? "desk-score-confirmed" : "",
    confirmed && stamped ? "desk-score-stamp" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className="review">
      {confirmed && <PrintControls examId={examId} scriptId={scriptId} />}
      <div className="desk-bar">
        <div className="desk-who">
          <p className="desk-crumb">
            <Link to={`/exams/${String(examId)}/queue`}>{review.exam.title}</Link>
            {" · "}
            <span className="desk-progress">
              {t("review.positionOf", {
                position: review.navigation.position,
                count: review.navigation.count,
              })}
            </span>
          </p>
          <h1 className="desk-student">
            <span>{name}</span> <span className="code">{review.script.student_code}</span>
            <span className={`badge badge-script-${review.script.status}`}>
              {confirmed && <Icon name="check" size={14} />}
              {t(`scriptStatus.${review.script.status}`)}
            </span>
          </h1>
        </div>

        <div className="desk-total" aria-live="polite">
          <p className={scoreClass}>
            <span className="visually-hidden">
              {t("review.totals", { final: finalTotal ?? "–", max: review.totals.max_total })}
            </span>
            <span className="desk-score-label" aria-hidden="true">
              {t("review.totalLabel")}
            </span>
            <span
              className={
                finalTotal === null ? "desk-score-value desk-score-empty" : "desk-score-value"
              }
              aria-hidden="true"
            >
              {finalTotal ?? "–"}
            </span>
            <span className="desk-score-max" aria-hidden="true">
              / {review.totals.max_total}
            </span>
          </p>
          <div className="desk-meta">
            <p className="desk-progress">
              {t("review.decided", {
                decided: review.totals.decided_points,
                total: review.totals.total_points,
              })}
            </p>
            {review.totals.deductions > 0 && (
              <p className="deduction-summary">
                {t("review.deductionsTotal", {
                  count: review.totals.deductions,
                  marks: review.totals.marks_deducted,
                })}
              </p>
            )}
          </div>
        </div>

        <div className="desk-actions">
          <button
            type="button"
            className="button-secondary icon-button"
            aria-label={t("review.previousScript")}
            title={`${t("review.previousScript")} (K)`}
            disabled={review.navigation.previous_id === null}
            onClick={() => {
              goToScript(review.navigation.previous_id);
            }}
          >
            <Icon name="prev" />
          </button>
          <button
            type="button"
            className="button-secondary icon-button"
            aria-label={t("review.nextScript")}
            title={`${t("review.nextScript")} (J)`}
            disabled={review.navigation.next_id === null}
            onClick={() => {
              goToScript(review.navigation.next_id);
            }}
          >
            <Icon name="next" />
          </button>
          <button
            type="button"
            className="button-quiet icon-button"
            aria-label={t("review.shortcuts")}
            title={`${t("review.shortcuts")} (?)`}
            onClick={() => {
              setHelp(true);
            }}
          >
            <Icon name="keyboard" size={20} />
          </button>
          {review.ready && !review.locked && (
            <ConfirmButton
              label={t("rerun.script")}
              question={t("rerun.scriptQuestion")}
              disabled={busy}
              onConfirm={() => {
                run(() => api.rerunScript(scriptId), t("rerun.scriptStarted"));
              }}
            />
          )}
          {review.locked ? (
            <button type="button" className="button-secondary" disabled={busy} onClick={reopen}>
              <Icon name="undo" />
              {t("review.reopen")}
            </button>
          ) : (
            <button
              type="button"
              className="primary"
              disabled={busy || !review.can_confirm}
              title={review.can_confirm ? undefined : t("review.cannotConfirm")}
              onClick={confirm}
            >
              <Icon name="check" />
              {t("review.confirm")}
            </button>
          )}
        </div>
      </div>

      <div className="desk-messages">
        {review.test_model && <TestModelBanner />}
        {review.script.manual_reason && (
          <p className="notice notice-warning" role="status">
            {t("review.manualMarking")}{" "}
            {t(`ai.manualReason.${review.script.manual_reason}`, {
              defaultValue: t("ai.manualReason.unknown"),
            })}
          </p>
        )}
        {!review.ready && (
          <p className="notice notice-warning" role="status">
            {t("review.notReady")}
          </p>
        )}
        {review.locked && (
          <p className="notice notice-confirmed" role="status">
            {t("review.lockedNotice")}
          </p>
        )}
        {review.marked_on_earlier_text && (
          <p className="notice notice-warning" role="status">
            {t("review.markedOnEarlierText")}
          </p>
        )}
        <ErrorMessage error={error} />
        {notice && (
          <p
            className={notice.tone === "confirmed" ? "notice notice-confirmed" : "notice"}
            role="status"
          >
            {notice.text}
          </p>
        )}
      </div>

      <div className="review-columns">
        <div className="review-left">
          {page ? (
            <PageViewer
              page={page}
              pages={review.pages}
              pageIndex={pageIndex}
              view={view}
              locked={!editable}
              busy={busy}
              onView={setView}
              onPage={goToPage}
              onRotate={(delta) => {
                rotateBy(page.id, delta);
              }}
              onResetRotation={() => {
                run(() => api.rotatePage(page.id, null));
              }}
              onUndoAuto={() => {
                run(() => api.undoAutoRotation(page.id));
              }}
              onRetranscribe={() => {
                run(() => api.retranscribePage(page.id), t("review.viewer.rereadQueued"));
              }}
              redPen={redPenOn ? pageMarks : undefined}
              redPenOn={redPenOn}
              onRedPen={switchRedPen}
              evidence={evidenceBands}
              showEvidence={showEvidence}
              onShowEvidence={setShowEvidence}
            />
          ) : (
            <p className="panel empty-state">{t("review.noPages")}</p>
          )}
        </div>

        <div className="review-right">
          {review.questions.length > 1 && (
            <nav className="question-nav" aria-label={t("review.questions")}>
              <ol>
                {review.questions.map((question) => {
                  const decided = question.points.every(
                    (p) => p.final_marks !== null && p.final_category !== null,
                  );
                  return (
                    <li key={question.id}>
                      <button
                        type="button"
                        aria-current={question.id === currentQuestion?.id ? "true" : undefined}
                        aria-label={t("review.questionNav", {
                          label: question.label,
                          final: question.final_total ?? "–",
                          max: question.max_marks,
                        })}
                        onClick={() => {
                          goToQuestion(question.id);
                        }}
                      >
                        <span className={decided ? "qn-decided" : undefined}>{question.label}</span>
                        <span className="qn-score">
                          {question.final_total ?? "–"}/{question.max_marks}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>
          )}

          {currentQuestion && (
            <div className="checklist">
              <div className="question-head">
                <h2>
                  {t("review.questionTitle", { label: currentQuestion.label })}{" "}
                  <span className="question-score">
                    {t("review.questionTotal", {
                      final: currentQuestion.final_total ?? "–",
                      max: currentQuestion.max_marks,
                    })}
                  </span>
                </h2>
                {currentQuestion.deductions > 0 && (
                  <span className="deduction-summary">
                    {t("review.questionDeducted", {
                      count: currentQuestion.deductions,
                      marks: currentQuestion.marks_deducted,
                    })}
                  </span>
                )}
              </div>
              {currentQuestion.prompt_text && (
                <p className="question-prompt">{currentQuestion.prompt_text}</p>
              )}
              <ol className="points">
                {currentQuestion.points.map((point) => {
                  const index = points.findIndex((p) => p.point.id === point.id);
                  const item = points[index];
                  if (!item) return null;
                  return (
                    <PointRow
                      key={point.id}
                      item={item}
                      focused={index === focus}
                      editable={editable}
                      busy={busy}
                      lines={evidenceLocation(review.pages, point.evidence)}
                      itemRef={(el) => {
                        if (el) pointItems.current.set(point.id, el);
                        else pointItems.current.delete(point.id);
                      }}
                      onFocus={() => {
                        setFocus(index);
                      }}
                      onMarks={(marks) => {
                        setMarks(item, marks);
                      }}
                      onCategory={(category) => {
                        setCategory(item, category);
                      }}
                      onAccept={() => {
                        accept(item);
                      }}
                    />
                  );
                })}
              </ol>
              <label className="field question-comment">
                <span className="field-label">{t("review.comment")}</span>
                <input
                  key={`${String(currentQuestion.id)}-${currentQuestion.comment}`}
                  ref={(el) => {
                    if (el) comments.current.set(currentQuestion.id, el);
                    else comments.current.delete(currentQuestion.id);
                  }}
                  type="text"
                  maxLength={300}
                  defaultValue={currentQuestion.comment}
                  disabled={!editable}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === "Escape") e.currentTarget.blur();
                  }}
                  onBlur={(e) => {
                    const text = e.currentTarget.value.trim();
                    if (text !== currentQuestion.comment) {
                      const questionId = currentQuestion.id;
                      run(() => api.setComment(scriptId, questionId, text));
                    }
                  }}
                />
                <span className="field-hint">{t("review.commentHint")}</span>
              </label>
              {editable && (
                <div className="actions">
                  {review.exam.show_scheme_to_students && (
                    <button
                      type="button"
                      className="button-secondary button-small"
                      disabled={
                        busy ||
                        !currentQuestion.points.some((p) => {
                          const marks = p.final_marks ?? p.proposed_marks;
                          return marks !== null && marks < p.max_marks;
                        })
                      }
                      onClick={() => {
                        suggestComment(currentQuestion);
                      }}
                    >
                      <Icon name="pen" size={16} />
                      {t("redPen.suggest")}
                    </button>
                  )}
                  <button
                    type="button"
                    className="button-secondary button-small"
                    disabled={busy}
                    onClick={acceptAll}
                  >
                    {t("review.acceptAll")}
                  </button>
                </div>
              )}
            </div>
          )}

          {page && !page.is_cover && (
            <TranscriptionPanel
              page={page}
              evidence={showEvidence ? (current?.point.evidence ?? "") : ""}
              lines={highlightLines}
              editing={editing}
              editable={editable}
              draft={draft}
              busy={busy}
              textarea={textarea}
              onDraft={setDraft}
              onStart={startEditing}
              onSave={saveTranscription}
              onCancel={() => {
                setEditing(false);
              }}
            />
          )}
        </div>
      </div>

      {help && (
        <ShortcutHelp
          onClose={() => {
            setHelp(false);
          }}
        />
      )}
    </section>
  );
}

function PointRow({
  item,
  focused,
  editable,
  busy,
  lines,
  itemRef,
  onFocus,
  onMarks,
  onCategory,
  onAccept,
}: {
  item: FlatPoint;
  focused: boolean;
  editable: boolean;
  busy: boolean;
  lines: { pageIndex: number; lines: number[] } | null;
  itemRef: (el: HTMLLIElement | null) => void;
  onFocus: () => void;
  onMarks: (marks: number) => void;
  onCategory: (category: ErrorCategory) => void;
  onAccept: () => void;
}) {
  const { t } = useTranslation();
  const { point } = item;
  const classes = ["point"];
  if (focused) classes.push("point-focused");
  if (point.deducted > 0) classes.push("point-deducted");
  if (point.final_marks !== null && point.final_category !== null) classes.push("point-decided");
  const options = Array.from({ length: Math.floor(point.max_marks) + 1 }, (_, i) => i);

  return (
    // Clicking anywhere on the point moves the keyboard focus there; keyboard users use ↑/↓.
    <li
      ref={itemRef}
      className={classes.join(" ")}
      aria-current={focused ? "true" : undefined}
      data-point-id={point.id}
      onClick={onFocus}
    >
      <span className="point-sign">
        <PenSign point={point} />
      </span>
      <div className="point-head">
        <span className="point-description">
          {point.description}
          {point.teacher_only && (
            <strong className="status-warning"> · {t("schemeRules.teacher_only")}</strong>
          )}
        </span>
        <span className="point-max">{t("review.pointMax", { max: point.max_marks })}</span>
        {point.deducted > 0 && (
          <span
            className="deduction-badge"
            title={t("review.deductedTitle", { count: point.deducted })}
            aria-label={t("review.deductedTitle", { count: point.deducted })}
          >
            −{point.deducted}
          </span>
        )}
      </div>
      {point.alternatives.length > 0 && (
        <p className="muted small">
          {t("review.alsoAccept", { alternatives: point.alternatives.join("; ") })}
        </p>
      )}
      {point.proposed_marks !== null ? (
        <div className="proposal">
          <span className="proposal-ai">
            {t("review.aiProposal", { marks: point.proposed_marks, max: point.max_marks })}
          </span>
          {point.error_category && (
            <span className={`category category-${point.error_category}`}>
              {t(`category.${point.error_category}`)}
            </span>
          )}
          {point.confidence !== null && (
            <span className={point.confidence < 0.6 ? "confidence low" : "confidence"}>
              {t("review.confidence", { percent: Math.round(point.confidence * 100) })}
            </span>
          )}
          {lines && (
            <span className="evidence-lines">
              {t("review.evidenceLines", {
                count: lines.lines.length,
                lines: formatLines(lines.lines),
                page: lines.pageIndex + 1,
              })}
            </span>
          )}
          {point.evidence && <q className="evidence">{point.evidence}</q>}
          <ModelLabel
            name={point.model_name}
            version={point.model_version}
            prompt={point.prompt_version}
          />
        </div>
      ) : (
        <p className="muted small">{t("review.noProposalShort")}</p>
      )}
      <div className="decision">
        <span className="field-label">{t("review.teacherMarks")}</span>
        <div className="marks-buttons" role="group" aria-label={t("review.teacherMarks")}>
          {options.map((marks) => (
            <button
              key={marks}
              type="button"
              aria-pressed={point.final_marks === marks}
              disabled={!editable || busy}
              onClick={(e) => {
                e.stopPropagation();
                onFocus();
                onMarks(marks);
              }}
            >
              {marks}
            </button>
          ))}
        </div>
        <select
          aria-label={t("review.teacherCategory")}
          value={point.final_category ?? ""}
          disabled={!editable || busy}
          onChange={(e) => {
            const value = ERROR_CATEGORIES.find((c) => c === e.target.value);
            if (value) onCategory(value);
          }}
        >
          <option value="">{t("review.chooseCategory")}</option>
          {ERROR_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {t(`category.${category}`)}
            </option>
          ))}
        </select>
        {point.proposed_marks !== null && (
          <button
            type="button"
            disabled={!editable || busy}
            onClick={(e) => {
              e.stopPropagation();
              onFocus();
              onAccept();
            }}
          >
            {t("review.accept")}
          </button>
        )}
      </div>
    </li>
  );
}

const RED_PEN_KEY = "margin.redPen";

function readRedPenSetting(): boolean {
  try {
    return window.localStorage.getItem(RED_PEN_KEY) !== "off";
  } catch {
    return true;
  }
}

/** The red ✓ / ✗ for a point, as the student will see it. Lighter while it is only the AI's
 * proposal. Its label says it in words, so colour is never the only signal. */
function PenSign({ point }: { point: ReviewPoint }) {
  const { t } = useTranslation();
  const marks = point.final_marks ?? point.proposed_marks;
  if (marks === null) return null;
  const pending = point.final_marks === null;
  const sign =
    marks >= point.max_marks
      ? "✓"
      : marks === 0
        ? "✗"
        : `${String(marks)}/${String(point.max_marks)}`;
  const label =
    marks >= point.max_marks
      ? t("redPen.signFull")
      : marks === 0
        ? t("redPen.signNone")
        : t("redPen.signPart", { marks, max: point.max_marks });
  return (
    <span
      className={pending ? "pen-sign pen-sign-pending" : "pen-sign"}
      title={label}
      aria-label={label}
    >
      {sign}
    </span>
  );
}

function TranscriptionPanel({
  page,
  evidence,
  lines,
  editing,
  editable,
  draft,
  busy,
  textarea,
  onDraft,
  onStart,
  onSave,
  onCancel,
}: {
  page: ReviewPage;
  evidence: string;
  lines: number[];
  editing: boolean;
  editable: boolean;
  draft: string;
  busy: boolean;
  textarea: RefObject<HTMLTextAreaElement | null>;
  onDraft: (text: string) => void;
  onStart: () => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const text = page.transcription?.text ?? "";
  const source = page.transcription?.source;
  // Each of the student's lines with its number, the evidence lines marked, matches inside.
  const segments = highlight(text, evidence);
  const rendered: { key: string; parts: { text: string; mark: boolean }[] }[] = [
    { key: "0", parts: [] },
  ];
  for (const segment of segments) {
    segment.text.split("\n").forEach((part, index) => {
      if (index > 0) rendered.push({ key: String(rendered.length), parts: [] });
      if (part) rendered.at(-1)?.parts.push({ text: part, mark: segment.mark });
    });
  }

  return (
    <div className="transcription">
      <div className="question-head">
        <h2>{t("review.transcription")}</h2>
        {source && (
          <span className="muted small">
            {source === "teacher" ? t("review.teacherVersion") : t("review.modelVersion")}
          </span>
        )}
      </div>
      {page.transcription?.source === "model" && (
        <p>
          <ModelLabel
            name={page.transcription.model_name}
            version={page.transcription.model_version}
            prompt={page.transcription.prompt_version}
          />
        </p>
      )}
      {editing ? (
        <>
          <textarea
            ref={textarea}
            className="transcription-editor"
            aria-label={t("review.transcription")}
            value={draft}
            rows={Math.max(6, draft.split("\n").length + 1)}
            onChange={(e) => {
              onDraft(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") e.currentTarget.blur();
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                onSave();
              }
            }}
          />
          <p className="field-hint">{t("review.editHint")}</p>
          <div className="actions">
            <button type="button" className="primary" disabled={busy} onClick={onSave}>
              {t("review.saveTranscription")}
            </button>
            <button type="button" className="button-secondary" onClick={onCancel}>
              {t("common.cancel")}
            </button>
          </div>
        </>
      ) : (
        <>
          {text ? (
            <ol className="transcription-lines" aria-label={t("review.transcriptionLines")}>
              {rendered.map((line, index) => (
                <li
                  key={line.key}
                  className={lines.includes(index + 1) ? "line-evidence" : undefined}
                >
                  <span className="line-number" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span>
                    {line.parts.map((part, partIndex) =>
                      part.mark ? (
                        <mark key={partIndex}>{part.text}</mark>
                      ) : (
                        <span key={partIndex}>{part.text}</span>
                      ),
                    )}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">{t("review.noTranscription")}</p>
          )}
          {editable && (
            <div className="actions">
              <button
                type="button"
                className="button-secondary button-small"
                disabled={busy}
                onClick={onStart}
              >
                <Icon name="pen" size={16} />
                {t("review.editTranscription")}
              </button>
            </div>
          )}
        </>
      )}
      {page.versions.length > 1 && (
        <details>
          <summary>{t("review.versions", { count: page.versions.length })}</summary>
          <ol className="versions">
            {page.versions.map((version) => (
              <li key={version.id}>
                <span className="muted">
                  {new Date(version.created_at).toLocaleString()} ·{" "}
                  {version.source === "teacher"
                    ? t("review.teacherVersion")
                    : t("review.modelVersion")}
                </span>{" "}
                <ModelLabel
                  name={version.model_name}
                  version={version.model_version}
                  prompt={version.prompt_version}
                />
                <pre className="transcription-text">{version.text}</pre>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

function ShortcutHelp({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
  }, []);
  return (
    <div className="dialog-backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="shortcut-title">
        <h2 id="shortcut-title">{t("review.shortcuts")}</h2>
        <p className="muted">{t("review.shortcutsHelp")}</p>
        <dl className="shortcut-list">
          {SHORTCUTS.map((shortcut) => (
            <div key={shortcut.label}>
              <dt>
                {shortcut.keys.map((key) => (
                  <kbd key={key}>{key}</kbd>
                ))}
              </dt>
              <dd>{t(shortcut.label)}</dd>
            </div>
          ))}
        </dl>
        <button ref={close} type="button" onClick={onClose}>
          {t("common.close")}
        </button>
      </div>
    </div>
  );
}

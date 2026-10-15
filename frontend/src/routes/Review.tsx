import { useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { api } from "../api/endpoints";
import type { ErrorCategory, ReviewPage, ScriptReview } from "../api/types";
import { ERROR_CATEGORIES } from "../api/types";
import { ErrorMessage, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { highlight } from "../review/evidence";
import { flatPoints, nextDeduction, step } from "../review/focus";
import type { FlatPoint } from "../review/focus";
import { actionForKey, isTypingTarget, SHORTCUTS } from "../review/keyboard";
import type { ReviewAction } from "../review/keyboard";
import { PageViewer } from "../review/PageViewer";
import { useHeartbeat } from "../review/useHeartbeat";
import { FIT, nextCategory, rotate, zoomIn, zoomOut } from "../review/viewer";

/** Screen 7: review one script. Everything can be done from the keyboard (`?` lists keys). */
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
  // Saves waiting to finish. Keys are never dropped: every change joins an ordered queue.
  const [pending, setPending] = useState(0);
  const busy = pending > 0;
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const comments = useRef(new Map<number, HTMLInputElement>());
  const pointItems = useRef(new Map<number, HTMLLIElement>());

  const editable = review.ready && !review.locked;
  useHeartbeat(scriptId, editable);

  const page = review.pages[pageIndex];
  const current: FlatPoint | undefined = points[focus];

  // When the focus moves to another point, keep it in view and show the page its evidence is on.
  const focusedId = current?.point.id;
  const focusedEvidence = current?.point.evidence ?? "";
  const pagesRef = useRef(review.pages);
  const editingRef = useRef(editing);
  useEffect(() => {
    pagesRef.current = review.pages;
    editingRef.current = editing;
  });
  useEffect(() => {
    if (focusedId === undefined) return;
    pointItems.current.get(focusedId)?.scrollIntoView({ block: "nearest" });
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
  ) => Promise<{ review: ScriptReview; notice?: string | undefined } | null>;

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
          if (result.notice) setNotice(result.notice);
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

  function setMarks(item: FlatPoint, marks: number) {
    if (marks > item.point.max_marks) {
      setNotice(t("review.marksTooHigh", { max: item.point.max_marks }));
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
      setNotice(t("review.noProposal"));
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
        setNotice(t("review.cannotConfirm"));
        return null;
      }
      return { review: await api.confirmScript(scriptId), notice: t("review.confirmed") };
    });
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
      setNotice(review.locked ? t("review.lockedNotice") : t("review.notReady"));
      return;
    }
    switch (action.type) {
      case "nextPoint":
      case "prevPoint":
        setFocus((f) => step(f, action.type === "nextPoint" ? 1 : -1, points.length));
        return;
      case "nextDeduction": {
        const next = nextDeduction(points, focus);
        if (next === null) setNotice(t("review.noDeductions"));
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
        if (current) comments.current.get(current.question.id)?.focus();
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
  return (
    <section className="review">
      <div className="review-header">
        <div>
          <p className="muted">
            <Link to={`/exams/${String(examId)}/queue`}>{review.exam.title}</Link> ·{" "}
            {t("review.positionOf", {
              position: review.navigation.position,
              count: review.navigation.count,
            })}
          </p>
          <h1>
            {name} <span className="code">{review.script.student_code}</span>{" "}
            <span className={`badge badge-script-${review.script.status}`}>
              {t(`scriptStatus.${review.script.status}`)}
            </span>
          </h1>
        </div>
        <div className="review-summary" aria-live="polite">
          <span>
            {t("review.totals", {
              final: review.totals.final_total ?? "–",
              max: review.totals.max_total,
            })}
          </span>
          <span className="muted">
            {t("review.decided", {
              decided: review.totals.decided_points,
              total: review.totals.total_points,
            })}
          </span>
          {review.totals.deductions > 0 && (
            <span className="deduction-summary">
              {t("review.deductionsTotal", {
                count: review.totals.deductions,
                marks: review.totals.marks_deducted,
              })}
            </span>
          )}
        </div>
        <div className="actions">
          <button
            type="button"
            disabled={review.navigation.previous_id === null}
            onClick={() => {
              goToScript(review.navigation.previous_id);
            }}
          >
            {t("review.previousScript")}
          </button>
          <button
            type="button"
            disabled={review.navigation.next_id === null}
            onClick={() => {
              goToScript(review.navigation.next_id);
            }}
          >
            {t("review.nextScript")}
          </button>
          <button
            type="button"
            onClick={() => {
              setHelp(true);
            }}
          >
            {t("review.shortcuts")}
          </button>
          {review.locked ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                run(() => api.reopenScript(scriptId), t("review.reopened"));
              }}
            >
              {t("review.reopen")}
            </button>
          ) : (
            <button
              type="button"
              className="primary"
              disabled={busy || !review.can_confirm}
              onClick={confirm}
            >
              {t("review.confirm")}
            </button>
          )}
        </div>
      </div>

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
        <p className="notice" role="status">
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
        <p className="notice" role="status">
          {notice}
        </p>
      )}

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
            />
          ) : (
            <p className="muted">{t("review.noPages")}</p>
          )}
        </div>

        <div className="review-right">
          {page && !page.is_cover && (
            <TranscriptionPanel
              page={page}
              evidence={current?.point.evidence ?? ""}
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

          {review.questions.map((question) => (
            <div key={question.id} className="card question">
              <div className="question-head">
                <h2>
                  {question.label}{" "}
                  <span className="muted">
                    {t("review.questionTotal", {
                      final: question.final_total ?? "–",
                      max: question.max_marks,
                    })}
                  </span>
                </h2>
                {question.deductions > 0 && (
                  <span className="deduction-summary">
                    {t("review.questionDeducted", {
                      count: question.deductions,
                      marks: question.marks_deducted,
                    })}
                  </span>
                )}
              </div>
              {question.prompt_text && <p className="muted">{question.prompt_text}</p>}
              <ol className="points">
                {question.points.map((point) => {
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
              <label className="field">
                <span className="field-label">{t("review.comment")}</span>
                <input
                  key={`${String(question.id)}-${question.comment}`}
                  ref={(el) => {
                    if (el) comments.current.set(question.id, el);
                    else comments.current.delete(question.id);
                  }}
                  type="text"
                  maxLength={300}
                  defaultValue={question.comment}
                  disabled={!editable}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === "Escape") e.currentTarget.blur();
                  }}
                  onBlur={(e) => {
                    const text = e.currentTarget.value.trim();
                    if (text !== question.comment) {
                      run(() => api.setComment(scriptId, question.id, text));
                    }
                  }}
                />
                <span className="field-hint">{t("review.commentHint")}</span>
              </label>
            </div>
          ))}
          {editable && (
            <div className="actions">
              <button type="button" disabled={busy} onClick={acceptAll}>
                {t("review.acceptAll")}
              </button>
            </div>
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
    // Clicking anywhere on the point moves the keyboard focus there; keyboard users use j/k.
    <li
      ref={itemRef}
      className={classes.join(" ")}
      aria-current={focused ? "true" : undefined}
      data-point-id={point.id}
      onClick={onFocus}
    >
      <div className="point-head">
        <span className="point-description">{point.description}</span>
        <span className="muted">{t("review.pointMax", { max: point.max_marks })}</span>
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
          <span>
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
          {point.evidence && <q className="evidence">{point.evidence}</q>}
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

function TranscriptionPanel({
  page,
  evidence,
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
  return (
    <div className="card transcription">
      <div className="question-head">
        <h2>{t("review.transcription")}</h2>
        {source && (
          <span className="muted">
            {source === "teacher" ? t("review.teacherVersion") : t("review.modelVersion")}
          </span>
        )}
      </div>
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
            <button type="button" onClick={onCancel}>
              {t("common.cancel")}
            </button>
          </div>
        </>
      ) : (
        <>
          {text ? (
            <pre className="transcription-text">
              {highlight(text, evidence).map((segment, index) =>
                segment.mark ? (
                  <mark key={index}>{segment.text}</mark>
                ) : (
                  <span key={index}>{segment.text}</span>
                ),
              )}
            </pre>
          ) : (
            <p className="muted">{t("review.noTranscription")}</p>
          )}
          {editable && (
            <div className="actions">
              <button type="button" disabled={busy} onClick={onStart}>
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
                </span>
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

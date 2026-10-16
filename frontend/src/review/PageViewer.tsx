import { useRef } from "react";
import type { PointerEvent, WheelEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints";
import type { RedPenMark, ReviewPage } from "../api/types";
import { Icon } from "../components/Icon";
import { PageOverlay } from "./RedPenOverlay";
import { isSideways, pan, transformFor, zoomIn, zoomOut, FIT } from "./viewer";
import type { ViewState } from "./viewer";

interface Props {
  page: ReviewPage;
  pages: ReviewPage[];
  pageIndex: number;
  view: ViewState;
  locked: boolean;
  busy: boolean;
  onView: (view: ViewState) => void;
  onPage: (index: number) => void;
  onRotate: (delta: 90 | -90) => void;
  onResetRotation: () => void;
  onUndoAuto: () => void;
  onRetranscribe: () => void;
  // Red pen marks for this page; undefined when switched off or not placed.
  redPen?: RedPenMark[] | undefined;
  redPenOn: boolean;
  onRedPen: (on: boolean) => void;
  // Where the selected point's evidence lines are on this page (rule-blue bands).
  evidence: RedPenMark[];
  showEvidence: boolean;
  onShowEvidence: (on: boolean) => void;
}

/** One page image with zoom (buttons, wheel, keyboard), pan (drag), rotation and a page strip.
 * The stored image is never changed: rotation is applied here with CSS. */
export function PageViewer(props: Props) {
  const { t } = useTranslation();
  const { page, view, onView } = props;
  const drag = useRef<{ x: number; y: number } | null>(null);
  const sideways = isSideways(page.rotation);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    drag.current = { x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const dx = event.clientX - drag.current.x;
    const dy = event.clientY - drag.current.y;
    drag.current = { x: event.clientX, y: event.clientY };
    onView(pan(view, dx, dy));
  }
  function onPointerUp() {
    drag.current = null;
  }
  function onWheel(event: WheelEvent<HTMLDivElement>) {
    onView(event.deltaY < 0 ? zoomIn(view) : zoomOut(view));
  }

  return (
    <div className="viewer">
      <div className="viewer-toolbar" role="toolbar" aria-label={t("review.viewer.toolbar")}>
        <span className="viewer-page">
          {t("review.viewer.pageOf", {
            page: props.pageIndex + 1,
            count: props.pages.length,
          })}
        </span>
        <span className="toolbar-group">
          <button
            type="button"
            onClick={() => {
              onView(zoomOut(view));
            }}
            aria-label={t("review.viewer.zoomOut")}
            title={`${t("review.viewer.zoomOut")} (−)`}
          >
            <Icon name="zoomOut" />
          </button>
          <span className="viewer-zoom">{Math.round(view.zoom * 100)}%</span>
          <button
            type="button"
            onClick={() => {
              onView(zoomIn(view));
            }}
            aria-label={t("review.viewer.zoomIn")}
            title={`${t("review.viewer.zoomIn")} (+)`}
          >
            <Icon name="zoomIn" />
          </button>
          <button
            type="button"
            onClick={() => {
              onView(FIT);
            }}
            aria-label={t("review.viewer.fit")}
            title={`${t("review.viewer.fit")} (F)`}
          >
            <Icon name="fit" />
          </button>
        </span>
        <span className="toolbar-sep" aria-hidden="true" />
        <span className="toolbar-group">
          <button
            type="button"
            disabled={props.locked || props.busy}
            onClick={() => {
              props.onRotate(-90);
            }}
            aria-label={t("review.viewer.rotateLeft")}
            title={`${t("review.viewer.rotateLeft")} (Shift+R)`}
          >
            <Icon name="rotateLeft" />
          </button>
          <button
            type="button"
            disabled={props.locked || props.busy}
            onClick={() => {
              props.onRotate(90);
            }}
            aria-label={t("review.viewer.rotateRight")}
            title={`${t("review.viewer.rotateRight")} (R)`}
          >
            <Icon name="rotateRight" />
          </button>
          {page.rotation_teacher !== null && (
            <button
              type="button"
              disabled={props.locked || props.busy}
              onClick={props.onResetRotation}
            >
              {t("review.viewer.resetRotation")}
            </button>
          )}
        </span>
        <span className="toolbar-sep" aria-hidden="true" />
        <button
          type="button"
          aria-pressed={props.showEvidence}
          title={`${t("review.viewer.evidence")} (E)`}
          onClick={() => {
            props.onShowEvidence(!props.showEvidence);
          }}
        >
          <Icon name={props.showEvidence ? "eye" : "eyeOff"} size={16} />
          {t("review.viewer.evidence")}
        </button>
        <label className="viewer-switch">
          <input
            type="checkbox"
            checked={props.redPenOn}
            onChange={(e) => {
              props.onRedPen(e.target.checked);
            }}
          />
          {t("redPen.show")}
        </label>
      </div>
      <div className="viewer-notices">
        {page.auto_rotated && (
          <p className="notice" role="status">
            <span className="badge badge-auto">{t("review.viewer.autoRotated")}</span>{" "}
            {t("review.viewer.autoRotatedHelp", {
              degrees: page.rotation_auto,
              confidence: Math.round((page.auto_rotation_confidence ?? 0) * 100),
            })}{" "}
            <button
              type="button"
              className="button-secondary button-small"
              disabled={props.locked || props.busy}
              onClick={props.onUndoAuto}
            >
              {t("review.viewer.undoAuto")}
            </button>
          </p>
        )}
        {page.rotated_after_transcription && !page.is_cover && (
          <p className="notice notice-warning" role="status">
            {page.retranscribe_pending
              ? t("review.viewer.rereadPending")
              : t("review.viewer.rotatedAfterTranscription")}{" "}
            {!page.retranscribe_pending && (
              <button
                type="button"
                className="button-secondary button-small"
                disabled={props.locked || props.busy}
                onClick={props.onRetranscribe}
              >
                {t("review.viewer.reread")}
              </button>
            )}
          </p>
        )}
      </div>
      <div
        className="viewer-stage"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onWheel={onWheel}
      >
        {/* The scan, its margin line, the evidence and the red pen move, zoom and turn together. */}
        <div
          className="viewer-sheet"
          data-testid="viewer-sheet"
          style={{ transform: transformFor(view, page.rotation) }}
        >
          <img
            className={sideways ? "viewer-image viewer-image-sideways" : "viewer-image"}
            src={api.pageImageUrl(page.id, "full")}
            alt={t("review.viewer.imageAlt", { page: props.pageIndex + 1 })}
            data-rotation={page.rotation}
            draggable={false}
          />
          {!page.is_cover && (
            <PageOverlay
              marks={props.redPen}
              evidence={props.evidence}
              width={page.width}
              height={page.height}
              rotation={page.rotation}
            />
          )}
        </div>
      </div>
      <ol className="page-strip" aria-label={t("review.viewer.strip")}>
        {props.pages.map((p, index) => (
          <li key={p.id}>
            <button
              type="button"
              className={index === props.pageIndex ? "page-thumb page-thumb-current" : "page-thumb"}
              aria-current={index === props.pageIndex ? "page" : undefined}
              aria-label={
                p.is_cover
                  ? t("review.viewer.coverThumb")
                  : t("review.viewer.pageThumb", { page: index + 1 })
              }
              onClick={() => {
                props.onPage(index);
              }}
            >
              <img
                src={api.pageImageUrl(p.id, "thumb")}
                alt=""
                loading="lazy"
                style={{ transform: `rotate(${String(p.rotation)}deg)` }}
              />
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

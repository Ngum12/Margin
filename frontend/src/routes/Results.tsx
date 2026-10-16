import { PrintControls } from "../components/SchoolHardware";
import { useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { api } from "../api/endpoints";
import type { ExportJob, Results as ResultsData } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorMessage, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { ExamHeader } from "../exam/ExamHeader";
import { ExportJobList } from "../exam/ExportJobs";
import { minutesSeconds } from "../review/focus";
import { nextSort, RETEACH_SHARE, sortRows, zeroShares } from "../results/table";
import type { Sort, SortKey } from "../results/table";
import { TestModelBadge, TestModelBanner } from "../review/ModelLabel";

/** Screen 8: class results and exports. Only confirmed scripts are ever exported. */
export default function Results() {
  const { t } = useTranslation();
  const examId = Number(useParams().examId);
  const { state } = useLoad(() => api.results(examId), [examId]);
  const [sort, setSort] = useState<Sort | null>(null);

  if (state.status === "error") return <ErrorMessage error={state.error} />;
  if (state.status === "loading") return <Loading />;
  const data = state.data;
  const exam = { id: data.exam_id, title: data.exam_title, status: data.exam_status };
  const rows = sortRows(data.rows, sort);
  const zeros = zeroShares(data);
  const ariaSort = (key: SortKey) => (sort?.key === key ? sort.direction : undefined);
  const sortHeader = (key: SortKey, children: ReactNode) => (
    <SortButton
      active={sort?.key === key ? sort.direction : null}
      onClick={() => {
        setSort(nextSort(sort, key));
      }}
    >
      {children}
    </SortButton>
  );

  return (
    <section>
      <ExamHeader exam={exam} />
      <PrintControls
        examId={examId}
        students={data.rows
          .filter((row) => row.confirmed)
          .map((row) => ({ id: row.script_id, name: row.student_name ?? row.student_code }))}
      />
      <div className="panel">
        <div className="panel-header">
          <h2>{t("results.title")}</h2>
          {data.confirmed_count > 0 && (
            <button
              type="button"
              className="button-secondary button-small"
              onClick={() => {
                window.print();
              }}
            >
              <Icon name="print" size={16} />
              {t("results.print")}
            </button>
          )}
        </div>
        <p>
          {t("results.confirmedCount", {
            confirmed: data.confirmed_count,
            count: data.script_count,
          })}
        </p>
        {data.confirmed_count < data.script_count && (
          <p className="notice notice-warning no-print">
            {t("results.notIncluded", { count: data.script_count - data.confirmed_count })}
          </p>
        )}
        {data.test_model_count > 0 && <TestModelBanner count={data.test_model_count} />}
        <ReviewTime data={data} />
        {data.rows.length === 0 ? (
          <p className="empty-state">{t("results.empty")}</p>
        ) : (
          <div className="table-wrap">
            <table className="results-table">
              <thead>
                <tr>
                  <th scope="col" aria-sort={ariaSort("student")}>
                    {sortHeader("student", t("queue.student"))}
                  </th>
                  {data.questions.map((q, index) => (
                    <th key={q.id} scope="col" className="num" aria-sort={ariaSort(index)}>
                      {sortHeader(
                        index,
                        <>
                          {q.label} <span className="max">/{q.max_marks}</span>
                        </>,
                      )}
                    </th>
                  ))}
                  <th scope="col" className="num" aria-sort={ariaSort("total")}>
                    {sortHeader(
                      "total",
                      <>
                        {t("results.total")} <span className="max">/{data.max_total}</span>
                      </>,
                    )}
                  </th>
                  <th scope="col" className="num" aria-sort={ariaSort("percentage")}>
                    {sortHeader("percentage", "%")}
                  </th>
                  <th scope="col" className="results-pdf">
                    <span className="visually-hidden">{t("results.markedPdf")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.script_id} className={row.confirmed ? undefined : "inactive"}>
                    <td>
                      {row.student_name && <span className="strong-link">{row.student_name}</span>}{" "}
                      <span className="code">{row.student_code}</span>
                      {row.test_model && (
                        <>
                          {" "}
                          <TestModelBadge />
                        </>
                      )}
                      {!row.confirmed && (
                        <span className="muted small"> · {t(`scriptStatus.${row.status}`)}</span>
                      )}
                    </td>
                    {row.marks.map((mark, index) => (
                      <td key={data.questions[index]?.id ?? index} className="num">
                        {mark ?? "—"}
                      </td>
                    ))}
                    <td className="num">
                      <strong>{row.total ?? "—"}</strong>
                    </td>
                    <td className="num">{row.percentage ?? "—"}</td>
                    <td className="results-pdf row-end">
                      {row.confirmed && (
                        <a
                          href={api.markedPdfUrl(row.script_id)}
                          download
                          aria-label={t("results.markedPdfFor", { code: row.student_code })}
                        >
                          {t("results.markedPdf")}
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              {data.confirmed_count > 0 && (
                <tfoot>
                  <tr>
                    <th scope="row">{t("results.average")}</th>
                    {data.questions.map((q) => (
                      <td key={q.id} className="num">
                        {q.average ?? "—"}
                      </td>
                    ))}
                    <td className="num">{data.average_total ?? "—"}</td>
                    <td colSpan={2} />
                  </tr>
                  <tr>
                    <th scope="row">{t("results.zeroShare")}</th>
                    {data.questions.map((q, index) => {
                      const share = zeros[index] ?? null;
                      const high = share !== null && share >= RETEACH_SHARE;
                      return (
                        <td key={q.id} className={high ? "num zero-share-high" : "num"}>
                          {share === null ? "—" : `${String(Math.round(share * 100))}%`}
                          {high && (
                            <>
                              {" "}
                              <Icon name="warning" size={14} />
                              <span className="visually-hidden">{t("results.reteach")}</span>
                            </>
                          )}
                        </td>
                      );
                    })}
                    <td colSpan={3} />
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        )}
        {data.confirmed_count > 0 && <p className="field-hint">{t("results.zeroShareHelp")}</p>}
      </div>
      <Exports examId={examId} data={data} />
    </section>
  );
}

function SortButton({
  active,
  onClick,
  children,
}: {
  active: "ascending" | "descending" | null;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className="sort" onClick={onClick}>
      {children}
      <Icon
        name={active === null ? "sort" : active === "ascending" ? "sortUp" : "sortDown"}
        size={14}
      />
    </button>
  );
}

function ReviewTime({ data }: { data: ResultsData }) {
  const { t } = useTranslation();
  if (data.timed_count === 0 || data.average_review_seconds === null) return null;
  return (
    <p>
      {t("queue.averageTime", { count: data.timed_count })}{" "}
      {t("queue.duration", minutesSeconds(data.average_review_seconds))}{" "}
      <span className="muted">
        ({t("queue.activeTime")}{" "}
        {t("queue.duration", minutesSeconds(data.average_active_seconds ?? 0))})
      </span>
    </p>
  );
}

function Exports({ examId, data }: { examId: number; data: ResultsData }) {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<ExportJob[]>(data.class_pdfs);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const none = data.confirmed_count === 0;

  async function requestClassPdf() {
    setBusy(true);
    setError(null);
    try {
      const job = await api.requestClassPdf(examId);
      setJobs((current) => [job, ...current]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel no-print">
      <h2>{t("results.exportsTitle")}</h2>
      <p className="muted">{t("results.exportsHelp")}</p>
      <div className="actions">
        {none ? (
          <span className="muted">{t("results.nothingToExport")}</span>
        ) : (
          <>
            <a className="button" href={api.resultsCsvUrl(examId)} download>
              <Icon name="download" />
              {t("results.downloadCsv")}
            </a>
            <button
              type="button"
              className="button-secondary"
              disabled={busy}
              onClick={() => void requestClassPdf()}
            >
              {t("results.classPdf")}
            </button>
          </>
        )}
      </div>
      <ErrorMessage error={error} />
      <ExportJobList jobs={jobs} />
    </div>
  );
}

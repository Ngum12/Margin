import { lazy, Suspense, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router";

import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
const Classes = lazy(() => import("./routes/admin/Classes"));
const ClassStudents = lazy(() => import("./routes/admin/ClassStudents"));
const TrainingData = lazy(() => import("./routes/admin/TrainingData"));
const Users = lazy(() => import("./routes/admin/Users"));
const CoverSheets = lazy(() => import("./routes/CoverSheets"));
const ExamSetup = lazy(() => import("./routes/ExamSetup"));
const Home = lazy(() => import("./routes/Home"));
const MarkingQueue = lazy(() => import("./routes/MarkingQueue"));
const NewExam = lazy(() => import("./routes/NewExam"));
const Queue = lazy(() => import("./routes/Queue"));
const Results = lazy(() => import("./routes/Results"));
const Scans = lazy(() => import("./routes/Scans"));
const Settings = lazy(() => import("./routes/Settings"));
const SignIn = lazy(() => import("./routes/SignIn"));

const Registers = lazy(() => import("./routes/Registers"));
const StudentPortal = lazy(() => import("./routes/StudentPortal"));
const Remarks = lazy(() => import("./routes/Remarks"));
const StudentAccess = lazy(() => import("./routes/StudentAccess"));
const Capture = lazy(() => import("./routes/Capture"));
const Review = lazy(() => import("./routes/Review"));

export default function App() {
  const { t, i18n } = useTranslation();

  useEffect(() => {
    document.documentElement.lang = i18n.language;
    document.title = t("app.title");
  }, [i18n.language, t]);

  return (
    <Layout>
      <Suspense
        fallback={
          <div className="page-message">
            <Loading />
          </div>
        }
      >
        <Routes>
          <Route
            path="/registers"
            element={
              <RequireAuth>
                <Registers />
              </RequireAuth>
            }
          />
          <Route path="/student/*" element={<StudentPortal />} />
          <Route
            path="/remarks"
            element={
              <RequireAuth>
                <Remarks />
              </RequireAuth>
            }
          />
          <Route
            path="/student-access"
            element={
              <RequireAuth>
                <StudentAccess />
              </RequireAuth>
            }
          />
          <Route path="/signin" element={<SignIn />} />
          <Route
            path="/capture"
            element={
              <RequireAuth>
                <Capture />
              </RequireAuth>
            }
          />
          <Route
            path="/"
            element={
              <RequireAuth>
                <Home />
              </RequireAuth>
            }
          />
          <Route
            path="/queue"
            element={
              <RequireAuth>
                <MarkingQueue />
              </RequireAuth>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAuth>
                <Settings />
              </RequireAuth>
            }
          />
          <Route
            path="/exams/new"
            element={
              <RequireAuth>
                <NewExam />
              </RequireAuth>
            }
          />
          <Route
            path="/exams/:examId"
            element={
              <RequireAuth>
                <ExamSetup />
              </RequireAuth>
            }
          />
          <Route
            path="/exams/:examId/sheets"
            element={
              <RequireAuth>
                <CoverSheets />
              </RequireAuth>
            }
          />
          <Route
            path="/exams/:examId/scans"
            element={
              <RequireAuth>
                <Scans />
              </RequireAuth>
            }
          />
          <Route
            path="/exams/:examId/queue"
            element={
              <RequireAuth>
                <Queue />
              </RequireAuth>
            }
          />
          <Route
            path="/exams/:examId/review/:scriptId"
            element={
              <RequireAuth>
                <Review />
              </RequireAuth>
            }
          />
          <Route
            path="/exams/:examId/results"
            element={
              <RequireAuth>
                <Results />
              </RequireAuth>
            }
          />
          <Route
            path="/admin/training-data"
            element={
              <RequireAuth admin>
                <TrainingData />
              </RequireAuth>
            }
          />
          <Route
            path="/admin/users"
            element={
              <RequireAuth admin>
                <Users />
              </RequireAuth>
            }
          />
          <Route
            path="/admin/classes"
            element={
              <RequireAuth admin>
                <Classes />
              </RequireAuth>
            }
          />
          <Route
            path="/admin/classes/:classId"
            element={
              <RequireAuth admin>
                <ClassStudents />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}

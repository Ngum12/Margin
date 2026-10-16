import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router";

import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import Classes from "./routes/admin/Classes";
import ClassStudents from "./routes/admin/ClassStudents";
import TrainingData from "./routes/admin/TrainingData";
import Users from "./routes/admin/Users";
import CoverSheets from "./routes/CoverSheets";
import ExamSetup from "./routes/ExamSetup";
import Home from "./routes/Home";
import MarkingQueue from "./routes/MarkingQueue";
import NewExam from "./routes/NewExam";
import Queue from "./routes/Queue";
import Results from "./routes/Results";
import Review from "./routes/Review";
import Scans from "./routes/Scans";
import Settings from "./routes/Settings";
import SignIn from "./routes/SignIn";

export default function App() {
  const { t, i18n } = useTranslation();

  useEffect(() => {
    document.documentElement.lang = i18n.language;
    document.title = t("app.title");
  }, [i18n.language, t]);

  return (
    <Layout>
      <Routes>
        <Route path="/signin" element={<SignIn />} />
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
    </Layout>
  );
}

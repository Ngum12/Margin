import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router";

import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import Classes from "./routes/admin/Classes";
import ClassStudents from "./routes/admin/ClassStudents";
import Users from "./routes/admin/Users";
import ExamSetup from "./routes/ExamSetup";
import Home from "./routes/Home";
import NewExam from "./routes/NewExam";
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

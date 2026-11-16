import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "@/layouts/AppLayout";
import { ProtectedRoute, PublicOnlyRoute } from "@/components/ProtectedRoute";
import { Spinner } from "@/components/ui";
import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import ForgotPasswordPage from "@/pages/auth/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/auth/ResetPasswordPage";
import VerifyEmailPage from "@/pages/auth/VerifyEmailPage";
import ChangePasswordPage from "@/pages/auth/ChangePasswordPage";
import NotificationsPage from "@/pages/NotificationsPage";
import ProfilePage from "@/pages/ProfilePage";
import NotFoundPage from "@/pages/NotFoundPage";

const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const EmployeesPage = lazy(() => import("@/pages/admin/EmployeesPage"));
const UsersPage = lazy(() => import("@/pages/admin/UsersPage"));
const AuditLogsPage = lazy(() => import("@/pages/admin/AuditLogsPage"));
const EmailLogsPage = lazy(() => import("@/pages/admin/EmailLogsPage"));
const SettingsPage = lazy(() => import("@/pages/admin/SettingsPage"));
const CategoriesPage = lazy(() => import("@/pages/recruitment/CategoriesPage"));
const OpeningsPage = lazy(() => import("@/pages/recruitment/OpeningsPage"));
const OpeningFormPage = lazy(() => import("@/pages/recruitment/OpeningFormPage"));
const OpeningDetailPage = lazy(() => import("@/pages/recruitment/OpeningDetailPage"));
const ApplicantsPage = lazy(() => import("@/pages/recruitment/ApplicantsPage"));
const ApplicantDetailPage = lazy(() => import("@/pages/recruitment/ApplicantDetailPage"));
const ApplicationsPage = lazy(() => import("@/pages/recruitment/ApplicationsPage"));
const ApplicationReviewPage = lazy(() => import("@/pages/recruitment/ApplicationReviewPage"));
const AssessmentsPage = lazy(() => import("@/pages/assessments/AssessmentsPage"));
const AssessmentDetailPage = lazy(() => import("@/pages/assessments/AssessmentDetailPage"));
const QuestionBankPage = lazy(() => import("@/pages/assessments/QuestionBankPage"));
const SchedulesPage = lazy(() => import("@/pages/scheduling/SchedulesPage"));
const ScheduleDetailPage = lazy(() => import("@/pages/scheduling/ScheduleDetailPage"));
const MyTestsPage = lazy(() => import("@/pages/tests/MyTestsPage"));
const MyTestDetailPage = lazy(() => import("@/pages/tests/MyTestDetailPage"));
const TokenRedirectPage = lazy(() => import("@/pages/tests/TokenRedirectPage"));
const TestRunnerPage = lazy(() => import("@/pages/tests/TestRunnerPage"));
const ResultsPage = lazy(() => import("@/pages/results/ResultsPage"));
const ResultDetailPage = lazy(() => import("@/pages/results/ResultDetailPage"));
const InterviewsPage = lazy(() => import("@/pages/interviews/InterviewsPage"));
const InterviewDetailPage = lazy(() => import("@/pages/interviews/InterviewDetailPage"));
const BulkBatchesPage = lazy(() => import("@/pages/bulk/BulkBatchesPage"));
const BulkBatchDetailPage = lazy(() => import("@/pages/bulk/BulkBatchDetailPage"));
const AnalyticsPage = lazy(() => import("@/pages/analytics/AnalyticsPage"));
const ComparePage = lazy(() => import("@/pages/analytics/ComparePage"));
const MyResultsPage = lazy(() => import("@/pages/results/MyResultsPage"));
const MyInterviewsPage = lazy(() => import("@/pages/interviews/MyInterviewsPage"));
const ProfileEditPage = lazy(() => import("@/pages/applicant/ProfileEditPage"));
const JobsPage = lazy(() => import("@/pages/applicant/JobsPage"));
const JobDetailPage = lazy(() => import("@/pages/applicant/JobDetailPage"));
const MyApplicationsPage = lazy(() => import("@/pages/applicant/MyApplicationsPage"));
const MyApplicationDetailPage = lazy(() => import("@/pages/applicant/MyApplicationDetailPage"));

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route element={<PublicOnlyRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Route>
        {/* Reachable whether or not signed in (links are opened from email) */}
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />

        <Route element={<ProtectedRoute roles={["applicant"]} />}>
          {/* outside AppLayout: distraction-free */}
          <Route path="/take/:attemptId" element={<TestRunnerPage />} />
          <Route path="/test/:token" element={<TokenRedirectPage />} />
        </Route>

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route element={<ProtectedRoute roles={["admin"]} />}>
              <Route path="/admin/employees" element={<EmployeesPage />} />
              <Route path="/admin/users" element={<UsersPage />} />
              <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
              <Route path="/admin/email-logs" element={<EmailLogsPage />} />
              <Route path="/admin/settings" element={<SettingsPage />} />
            </Route>
            <Route element={<ProtectedRoute roles={["admin", "employee"]} />}>
              <Route element={<ProtectedRoute permission="manage_job_openings" />}>
                <Route path="/openings/new" element={<OpeningFormPage />} />
                <Route path="/openings/:id/edit" element={<OpeningFormPage />} />
              </Route>
              <Route path="/openings" element={<OpeningsPage />} />
              <Route path="/openings/:id" element={<OpeningDetailPage />} />
              <Route path="/categories" element={<CategoriesPage />} />
              <Route path="/assessments" element={<AssessmentsPage />} />
              <Route path="/assessments/:id" element={<AssessmentDetailPage />} />
              <Route path="/question-bank" element={<QuestionBankPage />} />
              <Route element={<ProtectedRoute permission="bulk_upload_resumes" />}>
                <Route path="/bulk" element={<BulkBatchesPage />} />
                <Route path="/bulk/:id" element={<BulkBatchDetailPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="view_analytics" />}>
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/analytics/compare" element={<ComparePage />} />
              </Route>
              <Route element={<ProtectedRoute permission="review_results" />}>
                <Route path="/results" element={<ResultsPage />} />
                <Route path="/results/:id" element={<ResultDetailPage />} />
              </Route>
              <Route path="/interviews" element={<InterviewsPage />} />
              <Route path="/interviews/:id" element={<InterviewDetailPage />} />
              <Route element={<ProtectedRoute permission="schedule_tests" />}>
                <Route path="/schedules" element={<SchedulesPage />} />
                <Route path="/schedules/:id" element={<ScheduleDetailPage />} />
              </Route>
              <Route element={<ProtectedRoute permission="review_applications" />}>
                <Route path="/applicants" element={<ApplicantsPage />} />
                <Route path="/applicants/:id" element={<ApplicantDetailPage />} />
                <Route path="/applications" element={<ApplicationsPage />} />
                <Route path="/applications/:id" element={<ApplicationReviewPage />} />
              </Route>
            </Route>
            <Route element={<ProtectedRoute roles={["applicant"]} />}>
              <Route path="/applicant/profile" element={<ProfileEditPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/jobs/:id" element={<JobDetailPage />} />
              <Route path="/my-applications" element={<MyApplicationsPage />} />
              <Route path="/my-applications/:id" element={<MyApplicationDetailPage />} />
              <Route path="/my-results" element={<MyResultsPage />} />
              <Route path="/my-results/:id" element={<MyResultsPage />} />
              <Route path="/my-interviews" element={<MyInterviewsPage />} />
              <Route path="/my-tests" element={<MyTestsPage />} />
              <Route path="/my-tests/:id" element={<MyTestDetailPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}

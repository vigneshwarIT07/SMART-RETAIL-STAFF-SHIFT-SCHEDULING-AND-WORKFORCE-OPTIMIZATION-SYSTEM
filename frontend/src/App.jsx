import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './components/Toast';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Schedule from './pages/Schedule';
import Employees from './pages/Employees';
import Attendance from './pages/Attendance';
import Leave from './pages/Leave';
import Swaps from './pages/Swaps';
import Availability from './pages/Availability';
import Reports from './pages/Reports';
import Notifications from './pages/Notifications';
import StoreSettings from './pages/StoreSettings';
import { NotFound, StoreInfo, Unauthorized } from './pages/Misc';

function HomeRedirect() {
  const { isManager } = useAuth();
  return <Navigate to={isManager ? '/' : '/schedule'} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/store-info" element={<StoreInfo />} />
            <Route path="/unauthorized" element={<Unauthorized />} />
            <Route
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<ProtectedRoute roles={['manager']}><Dashboard /></ProtectedRoute>} />
              <Route path="/home" element={<HomeRedirect />} />
              <Route path="/schedule" element={<Schedule />} />
              <Route path="/employees" element={<ProtectedRoute roles={['manager']}><Employees /></ProtectedRoute>} />
              <Route path="/attendance" element={<Attendance />} />
              <Route path="/leave" element={<Leave />} />
              <Route path="/swaps" element={<Swaps />} />
              <Route path="/availability" element={<Availability />} />
              <Route path="/reports" element={<ProtectedRoute roles={['manager']}><Reports /></ProtectedRoute>} />
              <Route path="/notifications" element={<Notifications />} />
              <Route path="/store" element={<StoreSettings />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

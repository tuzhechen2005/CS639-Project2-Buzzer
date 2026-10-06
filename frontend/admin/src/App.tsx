import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate, NavLink } from 'react-router-dom';
import { BookOpen, Users, UserX, LogOut, History, Monitor, Smartphone } from 'lucide-react';
import LoginPage from './pages/LoginPage';
import CoursesPage from './pages/CoursesPage';
import UsersPage from './pages/UsersPage';
import UserDetailPage from './pages/UserDetailPage';
import GuestsPage from './pages/GuestsPage';
import SessionsPage from './pages/SessionsPage';

function RequireAdmin() {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function AdminLayout() {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? 'bg-accent-subtle text-accent-text'
        : 'text-fg-muted hover:bg-surface-raised hover:text-fg'
    }`;

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-surface border-r border-line flex flex-col">
        <div className="px-6 py-5 border-b border-line">
          <h1 className="text-lg font-bold text-fg">Buzzer Admin</h1>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          <NavLink to="/users" className={linkClass}>
            <Users size={16} /> Users
          </NavLink>
          <NavLink to="/courses" className={linkClass}>
            <BookOpen size={16} /> Courses
          </NavLink>
          <NavLink to="/guests" className={linkClass}>
            <UserX size={16} /> Guests
          </NavLink>
          <NavLink to="/sessions" className={linkClass}>
            <History size={16} /> Sessions
          </NavLink>

          {/* Host and player work happens in those apps; admins pass every check there.
              Plain links: they only work behind nginx (:8080), where the apps share a token. */}
          <div className="pt-5">
            <p className="px-4 pb-1 text-xs font-semibold uppercase tracking-wider text-fg-subtle">Host &amp; Play</p>
            <a href="/host/" className={linkClass({ isActive: false })}>
              <Monitor size={16} /> Host app
            </a>
            <a href="/player/" className={linkClass({ isActive: false })}>
              <Smartphone size={16} /> Player app
            </a>
          </div>
        </nav>
        <div className="p-3 border-t border-line">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium text-fg-muted hover:bg-surface-raised hover:text-fg w-full transition-colors"
          >
            <LogOut size={16} /> Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAdmin />}>
          <Route element={<AdminLayout />}>
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/:userId" element={<UserDetailPage />} />
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/guests" element={<GuestsPage />} />
            <Route path="/sessions" element={<SessionsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/users" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

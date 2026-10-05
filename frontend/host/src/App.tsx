import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import CourseLayout from './pages/course/CourseLayout';
import GamesTab from './pages/course/GamesTab';
import RosterTab from './pages/course/RosterTab';
import SessionsTab from './pages/course/SessionsTab';
import QuestionEditorPage from './pages/course/QuestionEditorPage';
import GameLayout from './pages/game/GameLayout';
import LobbyPage from './pages/game/LobbyPage';
import QuestionPage from './pages/game/QuestionPage';
import ResultsPage from './pages/game/ResultsPage';
import GameOverPage from './pages/game/GameOverPage';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  // Remember the page so LoginPage can return to it (e.g. a bookmarked roster URL).
  if (!localStorage.getItem('token')) return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}

// `/` and unknown paths: the course picker when signed in (the apps share the token on
// :8080, so an admin arriving from the admin app is already signed in), else login.
function DefaultRoute() {
  return <Navigate to={localStorage.getItem('token') ? '/home' : '/login'} replace />;
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/home" element={<RequireAuth><HomePage /></RequireAuth>} />
        <Route path="/courses/:courseId" element={<RequireAuth><CourseLayout /></RequireAuth>}>
          <Route index element={<Navigate to="games" replace />} />
          <Route path="games" element={<GamesTab />} />
          <Route path="games/:gameId/questions" element={<QuestionEditorPage />} />
          <Route path="roster" element={<RosterTab />} />
          <Route path="sessions" element={<SessionsTab />} />
        </Route>
        <Route path="/game/:code" element={<RequireAuth><GameLayout /></RequireAuth>}>
          <Route path="lobby" element={<LobbyPage />} />
          <Route path="question" element={<QuestionPage />} />
          <Route path="results" element={<ResultsPage />} />
          <Route path="gameover" element={<GameOverPage />} />
        </Route>
        <Route path="*" element={<DefaultRoute />} />
      </Routes>
    </BrowserRouter>
  );
}

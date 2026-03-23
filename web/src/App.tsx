import { useAuthStore } from './stores/authStore';
import { LoginPage } from './components/Auth/LoginPage';
import { AppShell } from './components/Layout/AppShell';

function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return isAuthenticated ? <AppShell /> : <LoginPage />;
}

export default App;

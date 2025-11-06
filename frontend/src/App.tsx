import { Route, Routes, Link } from 'react-router-dom';
import { useEffect } from 'react';
import HistoryPage from './pages/History';
import ThemeToggle from './components/ThemeToggle';
import Home from './pages/Home';

function App() {
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      document.documentElement.style.setProperty('--x', `${e.clientX}px`);
      document.documentElement.style.setProperty('--y', `${e.clientY}px`);
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  return (
    <div className="min-h-screen font-sans antialiased radial-gradient">
      <div className="relative flex flex-col min-h-screen">
        <header className="sticky top-0 z-50 w-full bg-background/80 backdrop-blur">
          <div className="container h-16 flex items-center justify-between">
            <nav className="flex items-center gap-6">
              <Link to="/" className="flex items-center gap-2 text-lg font-semibold">
                <span>WinkAi</span>
              </Link>
              <Link
                to="/history"
                className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                History
              </Link>
            </nav>
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1 container py-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/history" element={<HistoryPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default App;
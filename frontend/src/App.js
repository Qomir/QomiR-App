import React from 'react';
import './App.css';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Toaster } from './components/ui/sonner';
import { Header } from './components/Header';
import { Footer } from './components/Footer';
import { Home } from './pages/Home';
import { Forfaits } from './pages/Forfaits';
import { APropos } from './pages/APropos';
import { Contact } from './pages/Contact';

function App() {
  return (
    <div className="App bg-slate-950">
      <BrowserRouter>
        <Header />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/forfaits" element={<Forfaits />} />
          <Route path="/a-propos" element={<APropos />} />
          <Route path="/contact" element={<Contact />} />
        </Routes>
        <Footer />
        <Toaster position="top-right" />
      </BrowserRouter>
    </div>
  );
}

export default App;
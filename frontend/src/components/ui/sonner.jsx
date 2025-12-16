// src/components/ui/sonner.jsx
import React, { useEffect, useState } from 'react';
import { Toaster as Sonner, toast } from 'sonner';

// Détecte le thème actuel : "dark" si <html class="dark"> ou si l'OS est en dark mode
function detectTheme() {
  if (typeof window === 'undefined') return 'light';
  const hasDarkClass = document.documentElement.classList.contains('dark');
  if (hasDarkClass) return 'dark';
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'dark' : 'light';
}

const Toaster = (props) => {
  const [theme, setTheme] = useState(() => detectTheme());

  useEffect(() => {
    // Réagit au changement de préférence système
    const mql = window.matchMedia?.('(prefers-color-scheme: dark)');
    const onChange = () => setTheme(detectTheme());
    mql?.addEventListener?.('change', onChange);

    // Réagit aux changements de classe sur <html> (ex: ajout/suppression de "dark")
    const observer = new MutationObserver(() => setTheme(detectTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

    return () => {
      mql?.removeEventListener?.('change', onChange);
      observer.disconnect();
    };
  }, []);

  return (
    <Sonner
      theme={theme}               // "light" | "dark" | "system"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            'group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg',
          description: 'group-[.toast]:text-muted-foreground',
          actionButton:
            'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
          cancelButton:
            'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground',
        },
      }}
      {...props}
    />
  );
};

export { Toaster, toast };

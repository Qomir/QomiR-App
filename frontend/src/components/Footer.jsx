import React from 'react';
import { Link } from 'react-router-dom';
import { Mail, Phone, MapPin } from 'lucide-react';

export const Footer = () => {
  return (
    <footer className="bg-slate-950 border-t border-slate-800">
      <div className="container mx-auto px-4 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Logo & Description */}
          <div className="col-span-1 md:col-span-2">
            <img
              src="/logo.png"
              alt="QomiR App Logo"
              className="h-12 md-14 w-auto mb-4"
            />
            <p className="text-slate-400 text-sm mb-4 max-w-md">
              QomiR App révolutionne l'expérience restaurant en permettant aux clients de commander directement depuis leur table via QR code.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h3 className="text-white font-semibold mb-4">Navigation</h3>
            <ul className="space-y-2">
              <li>
                <Link to="/" className="text-slate-400 hover:text-sky-400 text-sm transition-colors">
                  Accueil
                </Link>
              </li>
              <li>
                <Link to="/forfaits" className="text-slate-400 hover:text-sky-400 text-sm transition-colors">
                  Forfaits
                </Link>
              </li>
              <li>
                <Link to="/a-propos" className="text-slate-400 hover:text-sky-400 text-sm transition-colors">
                  À propos
                </Link>
              </li>
              <li>
                <Link to="/contact" className="text-slate-400 hover:text-sky-400 text-sm transition-colors">
                  Contact
                </Link>
              </li>
            </ul>
          </div>

          {/* Contact Info */}
          <div>
            <h3 className="text-white font-semibold mb-4">Contact</h3>
            <ul className="space-y-3">
              <li className="flex items-center space-x-3 text-slate-400 text-sm">
                <Mail size={16} className="text-sky-400 flex-shrink-0" />
                <span>hello@qomirapp.com</span>
              </li>
              <li className="flex items-center space-x-3 text-slate-400 text-sm">
                
              </li>
              <li className="flex items-start space-x-3 text-slate-400 text-sm">
                <span>
              
                </span>
              </li>
            </ul>
          </div>
        </div>

        {/* Copyright */}
        <div className="border-t border-slate-800 mt-8 pt-8 text-center">
          <p className="text-slate-500 text-sm">
            © {new Date().getFullYear()} QomiR App. Tous droits réservés.
          </p>
        </div>
      </div>
    </footer>
  );
};
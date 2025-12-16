import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { QrCode, Zap, TrendingUp, CheckCircle2, ArrowRight, Smartphone, Users, Clock } from 'lucide-react';

export const Home = () => {
  const features = [
    {
      icon: QrCode,
      title: 'Commande par QR Code',
      description: 'Vos clients scannent le QR code sur leur table et accèdent instantanément au menu digital.'
    },
    {
      icon: Zap,
      title: 'Service Ultra-Rapide',
      description: 'Les commandes sont envoyées directement en cuisine ou au bar, réduisant les temps d\'attente.'
    },
    {
      icon: TrendingUp,
      title: 'Augmentez votre CA',
      description: 'Optimisez votre service et servez plus de clients avec la même équipe.'
    },
    {
      icon: Smartphone,
      title: 'Sans Application',
      description: 'Vos clients n\'ont besoin d\'aucune application, tout se passe dans leur navigateur.'
    },
    {
      icon: Users,
      title: 'Expérience Client',
      description: 'Offrez une expérience moderne et fluide qui fidélise votre clientèle.'
    },
    {
      icon: Clock,
      title: 'Gain de Temps',
      description: 'Votre équipe se concentre sur le service et la qualité plutôt que sur la prise de commandes.'
    }
  ];

  const benefits = [
    'Réduction des erreurs de commande',
    'Menu digital facilement modifiable',
    'Paiement intégré (optionnel)',
    'Statistiques et analytics en temps réel',
    'Support client réactif',
    'Mise en place rapide et simple'
  ];

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="relative pt-32 pb-20 lg:pt-40 lg:pb-32 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-950 to-black"></div>
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZGVmcz48cGF0dGVybiBpZD0iZ3JpZCIgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBwYXR0ZXJuVW5pdHM9InVzZXJTcGFjZU9uVXNlIj48cGF0aCBkPSJNIDQwIDAgTCAwIDAgMCA0MCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJyZ2JhKDI1NSwyNTUsMjU1LDAuMDMpIiBzdHJva2Utd2lkdGg9IjEiLz48L3BhdHRlcm4+PC9kZWZzPjxyZWN0IHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiIGZpbGw9InVybCgjZ3JpZCkiLz48L3N2Zz4=')] opacity-40"></div>
        
        <div className="container mx-auto px-4 lg:px-8 relative z-10">
          <div className="max-w-4xl mx-auto text-center">
            <div className="inline-block mb-6 animate-fade-in">
              <span className="inline-flex items-center space-x-2 px-4 py-2 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 text-sm font-medium">
                <Zap size={16} />
                <span>Solution SaaS pour Restaurants</span>
              </span>
            </div>
            
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white mb-6 animate-fade-in-up stagger-1">
              Fluidifiez votre restaurant avec
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-cyan-300"> QomiR App</span>
            </h1>
            
            <p className="text-lg md:text-xl text-slate-300 mb-8 max-w-2xl mx-auto animate-fade-in-up stagger-2">
              Permettez à vos clients de commander directement depuis leur table en scannant un QR code. Plus rapide, plus simple, plus moderne.
            </p>
            
            <div className="flex flex-col sm:flex-row gap-4 justify-center animate-fade-in-up stagger-3">
              <Link to="/contact">
                <Button size="lg" className="bg-sky-500 hover:bg-sky-600 text-white font-semibold px-8 py-6 text-lg group">
                  Demander une démo
                  <ArrowRight className="ml-2 group-hover:translate-x-1 transition-transform" size={20} />
                </Button>
              </Link>
              <Link to="/forfaits">
                <Button size="lg" variant="outline" className="border-slate-700 text-white hover:bg-slate-800 font-semibold px-8 py-6 text-lg">
                  Voir les forfaits
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-slate-900">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Une solution complète pour votre restaurant
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto">
              QomiR App transforme l'expérience de vos clients et optimise votre service
            </p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, index) => (
              <div
                key={index}
                className="group p-6 rounded-2xl bg-slate-800/50 border border-slate-700/50 hover:border-sky-500/50 transition-all duration-300 hover-lift"
              >
                <div className="w-12 h-12 rounded-xl bg-sky-500/10 flex items-center justify-center mb-4 group-hover:bg-sky-500/20 transition-colors">
                  <feature.icon className="text-sky-400" size={24} />
                </div>
                <h3 className="text-xl font-semibold text-white mb-2">{feature.title}</h3>
                <p className="text-slate-400">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="py-20 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
                Pourquoi choisir QomiR App ?
              </h2>
              <p className="text-slate-400 text-lg mb-8">
                Une solution pensée pour les restaurateurs modernes qui veulent offrir la meilleure expérience à leurs clients.
              </p>
              <div className="space-y-4">
                {benefits.map((benefit, index) => (
                  <div key={index} className="flex items-start space-x-3">
                    <CheckCircle2 className="text-sky-400 flex-shrink-0 mt-0.5" size={20} />
                    <span className="text-slate-300">{benefit}</span>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="relative">
              <div className="relative glass-effect rounded-2xl p-8 border border-slate-700">
                <div className="text-center">
                  <div className="w-24 h-24 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-sky-400 to-cyan-500 flex items-center justify-center">
                    <QrCode size={48} className="text-white" />
                  </div>
                  <h3 className="text-2xl font-bold text-white mb-3">Scanez & Commandez</h3>
                  <p className="text-slate-400 mb-6">
                    En quelques secondes, vos clients peuvent consulter le menu et passer leur commande
                  </p>
                  <div className="flex items-center justify-center space-x-4 text-sm">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-sky-400">30s</div>
                      <div className="text-slate-500">Mise en place</div>
                    </div>
                    <div className="w-px h-12 bg-slate-700"></div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-sky-400">0</div>
                      <div className="text-slate-500">Application requise</div>
                    </div>
                    <div className="w-px h-12 bg-slate-700"></div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-sky-400">100%</div>
                      <div className="text-slate-500">Digital</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-slate-900">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-4xl mx-auto text-center">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
              Prêt à moderniser votre restaurant ?
            </h2>
            <p className="text-slate-400 text-lg mb-8">
              Rejoignez les restaurateurs qui ont choisi QomiR App pour améliorer leur service
            </p>
            <Link to="/contact">
              <Button size="lg" className="bg-sky-500 hover:bg-sky-600 text-white font-semibold px-8 py-6 text-lg group">
                Contactez-nous
                <ArrowRight className="ml-2 group-hover:translate-x-1 transition-transform" size={20} />
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};
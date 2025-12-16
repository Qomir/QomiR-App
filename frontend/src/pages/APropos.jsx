import React from 'react';
import { Target, Eye, Award, Users2, Zap, TrendingUp } from 'lucide-react';

export const APropos = () => {
  const values = [
    {
      icon: Zap,
      title: 'Innovation',
      description: 'Nous repoussons les limites de la technologie pour offrir des solutions avant-gardistes.'
    },
    {
      icon: Users2,
      title: 'Satisfaction Client',
      description: 'Votre succès est notre priorité. Nous sommes à votre écoute pour vous accompagner.'
    },
    {
      icon: TrendingUp,
      title: 'Performance',
      description: 'Des outils optimisés pour maximiser votre efficacité opérationnelle.'
    },
    {
      icon: Award,
      title: 'Excellence',
      description: 'Nous visons l\'excellence dans chaque aspect de notre service.'
    }
  ];

  const advantages = [
    {
      title: 'Technologie Moderne',
      description: 'Une solution basée sur les dernières technologies web pour une expérience fluide et rapide.'
    },
    {
      title: 'Mise en Place Rapide',
      description: 'Déployez QomiR App en quelques minutes sans besoin de matériel coûteux.'
    },
    {
      title: 'Support Dédié',
      description: 'Notre équipe vous accompagne à chaque étape, de l\'installation à l\'utilisation quotidienne.'
    },
    {
      title: 'Évolutif',
      description: 'La solution grandit avec votre entreprise, du petit restaurant à la chaîne multi-sites.'
    }
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Hero Section */}
      <section className="pt-32 pb-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-4xl mx-auto text-center">
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 animate-fade-in-up">
              À propos de QomiR App
            </h1>
            <p className="text-lg text-slate-400 animate-fade-in-up stagger-1">
              La solution qui révolutionne l'expérience restaurant
            </p>
          </div>
        </div>
      </section>

      {/* Mission Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-5xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
              <div>
                <div className="flex items-center space-x-3 mb-4">
                  <div className="w-12 h-12 rounded-xl bg-sky-500/10 flex items-center justify-center">
                    <Target className="text-sky-400" size={24} />
                  </div>
                  <h2 className="text-3xl font-bold text-white">Notre Mission</h2>
                </div>
                <p className="text-slate-300 text-lg leading-relaxed mb-6">
                  Chez QomiR App, notre mission est de transformer l'expérience culinaire en digitalisant le processus de commande dans les restaurants. Nous croyons que la technologie doit simplifier la vie des restaurateurs et de leurs clients.
                </p>
                <p className="text-slate-400 leading-relaxed">
                  En permettant aux clients de commander directement depuis leur table via un simple QR code, nous réduisons les temps d'attente, minimisons les erreurs et permettons aux équipes de se concentrer sur l'essentiel : la qualité du service et la satisfaction client.
                </p>
              </div>
              
              <div className="glass-effect rounded-2xl p-8 border border-slate-700">
                <div className="flex items-center space-x-3 mb-6">
                  <div className="w-12 h-12 rounded-xl bg-sky-500/10 flex items-center justify-center">
                    <Eye className="text-sky-400" size={24} />
                  </div>
                  <h2 className="text-3xl font-bold text-white">Notre Vision</h2>
                </div>
                <p className="text-slate-300 leading-relaxed mb-4">
                  Devenir la solution de référence pour la digitalisation des restaurants en France et en Europe.
                </p>
                <p className="text-slate-400 leading-relaxed">
                  Nous imaginons un futur où chaque restaurant, quelle que soit sa taille, peut offrir une expérience digitale moderne à ses clients, améliorant ainsi leur satisfaction et optimisant les opérations.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Values Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-white mb-4">Nos Valeurs</h2>
              <p className="text-slate-400 text-lg">Les principes qui guident notre action au quotidien</p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {values.map((value, index) => (
                <div
                  key={index}
                  className="p-6 rounded-2xl bg-slate-800/50 border border-slate-700/50 hover:border-sky-500/50 transition-all duration-300 hover-lift"
                >
                  <div className="w-12 h-12 rounded-xl bg-sky-500/10 flex items-center justify-center mb-4">
                    <value.icon className="text-sky-400" size={24} />
                  </div>
                  <h3 className="text-xl font-semibold text-white mb-2">{value.title}</h3>
                  <p className="text-slate-400">{value.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-white mb-4">Comment fonctionne QomiR App ?</h2>
              <p className="text-slate-400 text-lg">Une solution simple et efficace</p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-sky-400 to-cyan-500 flex items-center justify-center text-white text-2xl font-bold">
                  1
                </div>
                <h3 className="text-xl font-semibold text-white mb-2">Le client scanne</h3>
                <p className="text-slate-400">
                  Avec son smartphone, le client scanne le QR code présent sur sa table
                </p>
              </div>
              
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-sky-400 to-cyan-500 flex items-center justify-center text-white text-2xl font-bold">
                  2
                </div>
                <h3 className="text-xl font-semibold text-white mb-2">Il commande</h3>
                <p className="text-slate-400">
                  Le menu s'affiche instantanément et le client passe sa commande en toute autonomie
                </p>
              </div>
              
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-sky-400 to-cyan-500 flex items-center justify-center text-white text-2xl font-bold">
                  3
                </div>
                <h3 className="text-xl font-semibold text-white mb-2">Vous recevez</h3>
                <p className="text-slate-400">
                  La commande arrive directement en cuisine ou au bar, prête à être préparée
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Advantages Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-5xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-white mb-4">Pourquoi nous choisir ?</h2>
              <p className="text-slate-400 text-lg">Les avantages de QomiR App</p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {advantages.map((advantage, index) => (
                <div
                  key={index}
                  className="p-6 rounded-2xl glass-effect border border-slate-700"
                >
                  <h3 className="text-xl font-semibold text-white mb-2">{advantage.title}</h3>
                  <p className="text-slate-400">{advantage.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-5xl mx-auto">
            <div className="glass-effect rounded-2xl p-12 border border-slate-700">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
                <div>
                  <div className="text-4xl font-bold text-sky-400 mb-2">30s</div>
                  <div className="text-slate-300 font-medium">Temps de mise en place</div>
                </div>
                <div>
                  <div className="text-4xl font-bold text-sky-400 mb-2">50%</div>
                  <div className="text-slate-300 font-medium">Réduction des erreurs</div>
                </div>
                <div>
                  <div className="text-4xl font-bold text-sky-400 mb-2">+35%</div>
                  <div className="text-slate-300 font-medium">Gain de productivité</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Check } from 'lucide-react';

export const Forfaits = () => {
  const plans = [
    {
      name: 'Essentiel',
      description: 'Les bases puissantes pour passer au niveau supérieur',
      features: [
        'Agent vocal intelligent',
        'Réservations automatisées',
        'Disponible 24/7',
        'Compte rendu automatique',
      ],
      highlight: false
    },
    {
      name: 'Light',
      description: 'Parfait pour les petits restaurants qui débutent',
      features: [
        'Menu digital avec QR code',
        'Interface de gestion basique',
        'Support par email',
        'Personnalisation du menu',
        'Statistiques mensuelles'
      ],
      highlight: false
    },
    {
      name: 'Pro',
      description: 'La solution idéale pour les restaurants actifs',
      features: [
        'Tout du forfait Light',
        'Interface avancée',
        'Support prioritaire',
        'Multi-langues',
        'Personnalisation avancée',
        'Gestion des allergènes',
      ],
      highlight: true
    },
    {
      name: 'Ultimate',
      description: 'Pour les établissements exigeants',
      features: [
        'Tout du forfait Pro',
        'Multi-établissements',
        'Support dédié 24/7',
        'Intégration caisse',
        'Gestion des stocks',
        'Rapports personnalisés'
      ],
      highlight: false
    }
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Hero Section */}
      <section className="pt-32 pb-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 animate-fade-in-up">
              Choisissez le forfait adapté à vos besoins
            </h1>
            <p className="text-lg text-slate-400 animate-fade-in-up stagger-1">
              Toutes nos solutions incluent les fonctionnalités essentielles pour moderniser votre restaurant. Contactez-nous pour discuter des tarifs.
            </p>
          </div>
        </div>
      </section>

      {/* Plans Section */}
      <section className="pb-20">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-7xl mx-auto">
            {plans.map((plan, index) => (
              <div
                key={index}
                className={`relative rounded-2xl p-8 transition-all duration-300 hover-lift ${
                  plan.highlight
                    ? 'bg-gradient-to-br from-sky-500/10 to-cyan-500/10 border-2 border-sky-500/50 shadow-xl shadow-sky-500/10'
                    : 'bg-slate-800/50 border border-slate-700/50'
                }`}
              >
                {plan.highlight && (
                  <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                    <span className="inline-block px-4 py-1 rounded-full bg-sky-500 text-white text-sm font-semibold">
                      Populaire
                    </span>
                  </div>
                )}
                
                <div className="text-center mb-8">
                  <h3 className="text-2xl font-bold text-white mb-2">{plan.name}</h3>
                  <p className="text-slate-400 text-sm">{plan.description}</p>
                </div>

                <ul className="space-y-4 mb-8">
                  {plan.features.map((feature, idx) => (
                    <li key={idx} className="flex items-start space-x-3">
                      <Check className="text-sky-400 flex-shrink-0 mt-0.5" size={18} />
                      <span className="text-slate-300 text-sm">{feature}</span>
                    </li>
                  ))}
                </ul>

                <Link to="/contact" className="block">
                  <Button
                    className={`w-full font-semibold ${
                      plan.highlight
                        ? 'bg-sky-500 hover:bg-sky-600 text-white'
                        : 'bg-slate-700 hover:bg-slate-600 text-white'
                    }`}
                  >
                    Nous contacter
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Additional Info Section */}
      <section className="pb-20">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-4xl mx-auto text-center">
            <div className="glass-effect rounded-2xl p-8 border border-slate-700">
              <h3 className="text-2xl font-bold text-white mb-4">
                Besoin d'un forfait sur mesure ?
              </h3>
              <p className="text-slate-400 mb-6">
                Nous proposons des solutions personnalisées pour les groupes de restaurants et les besoins spécifiques. Contactez notre équipe pour en discuter.
              </p>
              <Link to="/contact">
                <Button size="lg" className="bg-sky-500 hover:bg-sky-600 text-white font-semibold">
                  Discuter avec notre équipe
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

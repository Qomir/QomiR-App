import React, { useState } from 'react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { Mail, Phone, MapPin, Send } from 'lucide-react';
import { toast } from 'sonner';

export const Contact = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    restaurant: '',
    message: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    
    // Simulate form submission
    setTimeout(() => {
      toast.success('Message envoyé avec succès !', {
        description: 'Nous vous répondrons dans les plus brefs délais.'
      });
      setFormData({
        name: '',
        email: '',
        phone: '',
        restaurant: '',
        message: ''
      });
      setIsSubmitting(false);
    }, 1000);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Hero Section */}
      <section className="pt-32 pb-16">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6 animate-fade-in-up">
              Contactez-nous
            </h1>
            <p className="text-lg text-slate-400 animate-fade-in-up stagger-1">
              Une question ? Un projet ? Notre équipe est là pour vous aider
            </p>
          </div>
        </div>
      </section>

      {/* Contact Section */}
      <section className="pb-20">
        <div className="container mx-auto px-4 lg:px-8">
          <div className="max-w-5xl mx-auto">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* Contact Info */}
              <div className="lg:col-span-1 space-y-6">
                <div className="glass-effect rounded-2xl p-6 border border-slate-700">
                  <div className="flex items-start space-x-4">
                    <div className="w-12 h-12 rounded-xl bg-sky-500/10 flex items-center justify-center flex-shrink-0">
                      <Mail className="text-sky-400" size={24} />
                    </div>
                    <div>
                      <h3 className="text-white font-semibold mb-1">Email</h3>
                      <p className="text-slate-400 text-sm">hello@qomirapp.com</p>
                    </div>
                  </div>
                </div>

                

                </div>

              {/* Contact Form */}
              <div className="lg:col-span-2">
                <div className="glass-effect rounded-2xl p-8 border border-slate-700">
                  <h2 className="text-2xl font-bold text-white mb-6">Envoyez-nous un message</h2>
                  
                  <form onSubmit={handleSubmit} className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="name" className="text-slate-300">
                          Nom complet *
                        </Label>
                        <Input
                          id="name"
                          name="name"
                          value={formData.name}
                          onChange={handleChange}
                          required
                          className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
                          placeholder="Votre nom"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="email" className="text-slate-300">
                          Email *
                        </Label>
                        <Input
                          id="email"
                          name="email"
                          type="email"
                          value={formData.email}
                          onChange={handleChange}
                          required
                          className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
                          placeholder="votre@email.com"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <Label htmlFor="phone" className="text-slate-300">
                          Téléphone
                        </Label>
                        <Input
                          id="phone"
                          name="phone"
                          type="tel"
                          value={formData.phone}
                          onChange={handleChange}
                          className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
                          placeholder="+33 6 12 34 56 78"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="restaurant" className="text-slate-300">
                          Nom de l'établissement
                        </Label>
                        <Input
                          id="restaurant"
                          name="restaurant"
                          value={formData.restaurant}
                          onChange={handleChange}
                          className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
                          placeholder="Nom de votre établissement"
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="message" className="text-slate-300">
                        Message *
                      </Label>
                      <Textarea
                        id="message"
                        name="message"
                        value={formData.message}
                        onChange={handleChange}
                        required
                        rows={6}
                        className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500 resize-none"
                        placeholder="Parlez-nous de votre projet ou posez-nous vos questions..."
                      />
                    </div>

                    <Button
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full bg-sky-500 hover:bg-sky-600 text-white font-semibold py-6 text-base group"
                    >
                      {isSubmitting ? (
                        'Envoi en cours...'
                      ) : (
                        <>
                          Envoyer le message
                          <Send className="ml-2 group-hover:translate-x-1 transition-transform" size={18} />
                        </>
                      )}
                    </Button>
                  </form>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
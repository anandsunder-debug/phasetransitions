import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Truck, Shield, Leaf, Clock } from 'lucide-react';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { ProductCard } from '../components/products/ProductCard';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function HomePage() {
  const [featuredProducts, setFeaturedProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchProducts = async () => {
      try {
        const { data } = await axios.get(`${API}/products`);
        setFeaturedProducts(data.slice(0, 8));
      } catch (e) {
        // Error handled by empty state
      } finally {
        setLoading(false);
      }
    };
    fetchProducts();
  }, []);

  return (
    <div className="min-h-screen bg-[#F9F8F6]">
      {/* Hero Section */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 hero-gradient" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-6 z-10">
              <span className="text-xs uppercase tracking-[0.2em] text-[#2D5A27] font-semibold">
                Fresh & Organic
              </span>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-[#1A1A1A] font-['Outfit'] tracking-tight leading-none">
                Farm Fresh<br />
                <span className="text-[#2D5A27]">Groceries</span><br />
                Delivered
              </h1>
              <p className="text-lg text-[#6B6761] max-w-md leading-relaxed">
                Get the freshest organic produce and quality groceries delivered right to your doorstep. 
                Quality you can taste, convenience you deserve.
              </p>
              <div className="flex flex-wrap gap-4 pt-4">
                <Link to="/products">
                  <Button 
                    size="lg" 
                    className="bg-[#2D5A27] hover:bg-[#1E4219] text-white px-8 rounded-full"
                    data-testid="shop-now-button"
                  >
                    Shop Now
                    <ArrowRight className="w-5 h-5 ml-2" />
                  </Button>
                </Link>
              </div>
            </div>
            
            <div className="relative">
              <img
                src="https://images.unsplash.com/photo-1612362426802-dcc0ccd25f64?w=800"
                alt="Fresh vegetables"
                className="rounded-lg shadow-2xl"
              />
              <div className="absolute -bottom-4 -left-4 bg-white rounded-lg p-4 shadow-lg">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-[#2D5A27]/10 rounded-full flex items-center justify-center">
                    <Leaf className="w-6 h-6 text-[#2D5A27]" />
                  </div>
                  <div>
                    <p className="font-semibold text-[#1A1A1A]">100% Organic</p>
                    <p className="text-sm text-[#6B6761]">Certified products</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-12 bg-white border-y border-[#DCD7D0]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {[
              { icon: Truck, title: 'Free Delivery', desc: 'Orders over $50' },
              { icon: Shield, title: 'Secure Payment', desc: '100% protected' },
              { icon: Leaf, title: 'Organic Products', desc: 'Farm fresh quality' },
              { icon: Clock, title: 'Same Day', desc: 'Fast delivery' },
            ].map((feature) => (
              <div key={feature.title} className="flex items-center gap-4">
                <div className="w-12 h-12 bg-[#EBE8E3] rounded-full flex items-center justify-center flex-shrink-0">
                  <feature.icon className="w-5 h-5 text-[#2D5A27]" />
                </div>
                <div>
                  <p className="font-semibold text-[#1A1A1A] font-['Outfit']">{feature.title}</p>
                  <p className="text-sm text-[#6B6761]">{feature.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Featured Products */}
      <section className="py-16 lg:py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-end justify-between mb-8">
            <div>
              <span className="text-xs uppercase tracking-[0.2em] text-[#E47A53] font-semibold">
                Our Selection
              </span>
              <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-[#1A1A1A] font-['Outfit'] mt-2">
                Featured Products
              </h2>
            </div>
            <Link to="/products" className="text-[#2D5A27] font-medium hover:underline flex items-center gap-1">
              View All <ArrowRight className="w-4 h-4" />
            </Link>
          </div>

          {loading ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {[...Array(8)].map((_, i) => (
                <div key={`skeleton-${i}`} className="bg-white rounded-md border border-[#DCD7D0] p-4 animate-pulse">
                  <div className="aspect-square bg-[#EBE8E3] rounded-md mb-4" />
                  <div className="h-4 bg-[#EBE8E3] rounded w-1/3 mb-2" />
                  <div className="h-5 bg-[#EBE8E3] rounded w-2/3 mb-2" />
                  <div className="h-4 bg-[#EBE8E3] rounded w-full" />
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6" data-testid="featured-products">
              {featuredProducts.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 bg-[#2D5A27]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-white font-['Outfit'] mb-4">
            Fresh Groceries, Delivered Daily
          </h2>
          <p className="text-white/80 max-w-2xl mx-auto mb-8">
            Join thousands of happy customers who trust FreshCart for their daily grocery needs.
          </p>
          <Link to="/products">
            <Button 
              size="lg" 
              className="bg-white text-[#2D5A27] hover:bg-[#EBE8E3] px-8 rounded-full"
              data-testid="explore-products-button"
            >
              Explore Products
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}

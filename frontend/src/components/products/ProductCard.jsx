import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShoppingCart, Plus, Check, Zap } from 'lucide-react';
import { Button } from '../ui/button';
import { useCart } from '../../contexts/CartContext';
import { useAuth } from '../../contexts/AuthContext';
import { toast } from 'sonner';
import axios from 'axios';
import { prefetchProduct } from '../../lib/productCache';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function ProductCard({ product }) {
  const { addToCart } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [buyingNow, setBuyingNow] = useState(false);

  const handleAdd = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!user) {
      navigate('/login');
      return;
    }
    if (adding) return;
    setAdding(true);
    const result = await addToCart(product.id);
    setAdding(false);
    if (result.success) {
      setAdded(true);
      toast.success(`${product.name} added to cart`);
      setTimeout(() => setAdded(false), 1500);
    } else {
      toast.error(result.error || 'Failed to add');
    }
  };

  const handleBuyNow = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!user) {
      navigate('/login');
      return;
    }
    setBuyingNow(true);
    try {
      const { data } = await axios.post(`${API}/orders/buy-now`, null, {
        params: { product_id: product.id, quantity: 1 },
        withCredentials: true,
      });
      if (data.needs_delivery_info) {
        // First purchase — add to cart and go to checkout
        await addToCart(product.id);
        navigate('/checkout');
      } else {
        toast.success(`Ordered! $${data.total.toFixed(2)}`);
      }
    } catch (e) {
      toast.error('Failed — try adding to cart');
    } finally {
      setBuyingNow(false);
    }
  };

  return (
    <Link
      to={`/products/${product.id}`}
      className="group block"
      data-testid={`product-card-${product.id}`}
      onMouseEnter={() => prefetchProduct(product.id)}
    >
      <div className="bg-white rounded-xl border border-[#E8E4DE] overflow-hidden transition-all duration-200 hover:shadow-lg hover:border-[#2D5A27]/30 hover:-translate-y-1">
        <div className="relative h-44 bg-[#F5F3EF] overflow-hidden">
          <img
            src={product.image_url}
            alt={product.name}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
          <span className="absolute top-2 left-2 px-2 py-0.5 bg-white/90 text-[10px] text-[#5C5848] rounded-full font-medium tracking-wide uppercase">
            {product.category}
          </span>
        </div>

        <div className="p-4">
          <h3 className="font-semibold font-['Outfit'] text-[#1A1A1A] text-sm truncate">{product.name}</h3>
          <div className="flex items-end justify-between mt-2">
            <div>
              <span className="text-lg font-bold text-[#2D5A27] font-['JetBrains_Mono']">${product.price.toFixed(2)}</span>
              <span className="text-[10px] text-[#8A8A8E] ml-1">/{product.unit}</span>
            </div>
            <div className="flex gap-1.5">
              {/* Buy Now — instant purchase */}
              <Button
                size="sm"
                onClick={handleBuyNow}
                disabled={buyingNow}
                className="h-8 px-2.5 rounded-full bg-[#E47A53] text-white hover:bg-[#D06A43] text-[10px] font-semibold"
                data-testid={`buy-now-${product.id}`}
              >
                {buyingNow ? (
                  <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <><Zap className="w-3 h-3 mr-0.5" />Buy</>
                )}
              </Button>
              {/* Add to Cart */}
              <Button
                size="sm"
                onClick={handleAdd}
                disabled={adding}
                className={`h-8 w-8 p-0 rounded-full transition-all duration-200 ${
                  added 
                    ? 'bg-[#2D5A27] text-white' 
                    : 'bg-[#F5F3EF] text-[#2D5A27] hover:bg-[#2D5A27] hover:text-white'
                }`}
                data-testid={`add-to-cart-${product.id}`}
              >
                {adding ? (
                  <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                ) : added ? (
                  <Check className="w-3.5 h-3.5" />
                ) : (
                  <Plus className="w-3.5 h-3.5" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Link>
  );
}

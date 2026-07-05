import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus, Minus, ShoppingCart, Check, Zap } from 'lucide-react';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { useCart } from '../contexts/CartContext';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';
import { getCachedProduct } from '../lib/productCache';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ProductDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { user } = useAuth();
  
  // Try cache first for instant render
  const cached = getCachedProduct(id);
  const [product, setProduct] = useState(cached);
  const [loading, setLoading] = useState(!cached);
  const [quantity, setQuantity] = useState(1);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [buyingNow, setBuyingNow] = useState(false);

  useEffect(() => {
    // Always fetch fresh data, but if cached we already rendered
    const fetchProduct = async () => {
      try {
        const { data } = await axios.get(`${API}/products/${id}`);
        setProduct(data);
      } catch (e) {
        if (!product) {
          toast.error('Product not found');
          navigate('/products');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchProduct();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAddToCart = async () => {
    if (!user) {
      toast.error('Please sign in to add items to cart');
      navigate('/login');
      return;
    }

    setAdding(true);
    const result = await addToCart(product.id, quantity);
    setAdding(false);

    if (result.success) {
      setAdded(true);
      toast.success(`${quantity} x ${product.name} added to cart`);
      setTimeout(() => setAdded(false), 2000);
    } else {
      toast.error(result.error || 'Failed to add to cart');
    }
  };

  const handleBuyNow = async () => {
    if (!user) {
      navigate('/login');
      return;
    }
    setBuyingNow(true);
    try {
      const { data } = await axios.post(`${API}/orders/buy-now`, null, {
        params: { product_id: product.id, quantity },
        withCredentials: true,
      });
      if (data.needs_delivery_info) {
        await addToCart(product.id, quantity);
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="animate-pulse">
            <div className="h-8 w-32 bg-[#EBE8E3] rounded mb-8" />
            <div className="grid md:grid-cols-2 gap-8">
              <div className="aspect-square bg-[#EBE8E3] rounded-lg" />
              <div className="space-y-4">
                <div className="h-6 w-24 bg-[#EBE8E3] rounded" />
                <div className="h-10 w-2/3 bg-[#EBE8E3] rounded" />
                <div className="h-20 bg-[#EBE8E3] rounded" />
                <div className="h-8 w-32 bg-[#EBE8E3] rounded" />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!product) return null;

  return (
    <div className="min-h-screen bg-[#F9F8F6] py-8">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Back Button */}
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-[#6B6761] hover:text-[#1A1A1A] mb-8 transition-colors"
          data-testid="back-button"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Products
        </button>

        <div className="grid md:grid-cols-2 gap-8 lg:gap-12">
          {/* Image */}
          <div className="aspect-square rounded-lg overflow-hidden bg-white border border-[#DCD7D0]">
            <img
              src={product.image_url}
              alt={product.name}
              className="w-full h-full object-cover"
            />
          </div>

          {/* Details */}
          <div className="space-y-6">
            <div>
              <span className="text-xs uppercase tracking-[0.2em] text-[#E47A53] font-semibold">
                {product.category}
              </span>
              <h1 className="text-3xl sm:text-4xl font-bold text-[#1A1A1A] font-['Outfit'] mt-2">
                {product.name}
              </h1>
            </div>

            <p className="text-[#6B6761] leading-relaxed">
              {product.description}
            </p>

            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-[#2D5A27]">
                ${product.price.toFixed(2)}
              </span>
              <span className="text-[#6B6761]">/ {product.unit}</span>
            </div>

            <div className="flex items-center gap-2 text-sm text-[#6B6761]">
              <span className={`w-2 h-2 rounded-full ${product.stock > 0 ? 'bg-[#2D5A27]' : 'bg-red-500'}`} />
              {product.stock > 0 ? `${product.stock} in stock` : 'Out of stock'}
            </div>

            {/* Quantity Selector */}
            <div className="flex items-center gap-4">
              <span className="text-[#6B6761]">Quantity:</span>
              <div className="flex items-center border border-[#DCD7D0] rounded-md">
                <button
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  className="p-2 hover:bg-[#EBE8E3] transition-colors"
                  data-testid="quantity-decrease"
                >
                  <Minus className="w-4 h-4" />
                </button>
                <span className="w-12 text-center font-medium" data-testid="quantity-display">
                  {quantity}
                </span>
                <button
                  onClick={() => setQuantity(Math.min(product.stock, quantity + 1))}
                  className="p-2 hover:bg-[#EBE8E3] transition-colors"
                  data-testid="quantity-increase"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                size="lg"
                onClick={handleAddToCart}
                disabled={adding || product.stock === 0}
                className={`flex-1 sm:flex-none px-8 rounded-full transition-all ${
                  added 
                    ? 'bg-[#2D5A27] text-white' 
                    : 'bg-[#2D5A27] hover:bg-[#1E4219] text-white'
                }`}
                data-testid="add-to-cart-button"
              >
                {added ? (
                  <><Check className="w-5 h-5 mr-2" /> Added</>
                ) : (
                  <><ShoppingCart className="w-5 h-5 mr-2" /> Add to Cart</>
                )}
              </Button>
              <Button
                size="lg"
                onClick={handleBuyNow}
                disabled={buyingNow || product.stock === 0}
                className="flex-1 sm:flex-none px-8 rounded-full bg-[#E47A53] hover:bg-[#D06A43] text-white"
                data-testid="buy-now-button"
              >
                {buyingNow ? (
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <><Zap className="w-5 h-5 mr-2" /> Buy Now — ${(product.price * quantity).toFixed(2)}</>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useRef, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { MapPin, Phone, ShoppingBag, CheckCircle2, Zap } from 'lucide-react';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { useCart } from '../contexts/CartContext';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function CheckoutPage() {
  const { cart, cartTotal, clearCart } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [formData, setFormData] = useState({ delivery_address: '', phone: '' });
  const [processing, setProcessing] = useState(false);
  const [orderSuccess, setOrderSuccess] = useState(null);
  const [errors, setErrors] = useState({});
  const [prefsFetched, setPrefsFetched] = useState(false);
  const cartSnapshot = useRef(cart);

  if (cart.items.length > 0) {
    cartSnapshot.current = cart;
  }

  // Auto-fill from saved delivery preferences
  useEffect(() => {
    if (!user || prefsFetched) return;
    const fetchPrefs = async () => {
      try {
        const { data } = await axios.get(`${API}/user/delivery-preferences`, { withCredentials: true });
        if (data.address || data.phone) {
          setFormData({ delivery_address: data.address || '', phone: data.phone || '' });
        }
      } catch (e) {
        // No saved preferences yet — first-time checkout
        if (e?.response?.status && e.response.status !== 404) {
          console.error('Failed to fetch delivery preferences:', e);
        }
      }
      setPrefsFetched(true);
    };
    fetchPrefs();
  }, [user, prefsFetched]);

  const deliveryFee = cartTotal >= 50 ? 0 : 5;
  const total = cartTotal + deliveryFee;

  const validate = () => {
    const newErrors = {};
    if (!formData.delivery_address.trim()) {
      newErrors.delivery_address = 'Delivery address is required';
    }
    if (!formData.phone.trim()) {
      newErrors.phone = 'Phone number is required';
    } else if (!/^\+?[\d\s-]{7,}$/.test(formData.phone)) {
      newErrors.phone = 'Enter a valid phone number';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setProcessing(true);
    try {
      const { data } = await axios.post(`${API}/orders`, formData, { withCredentials: true });
      setOrderSuccess(data);
      clearCart();
      toast.success('Order placed!');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to place order');
    } finally {
      setProcessing(false);
    }
  };

  if (!user) {
    navigate('/login');
    return null;
  }

  if (orderSuccess) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-16">
        <div className="max-w-md mx-auto px-4 text-center">
          <CheckCircle2 className="w-16 h-16 text-[#2D5A27] mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-[#1A1A1A] font-['Outfit'] mb-2" data-testid="order-success-title">
            Order Confirmed!
          </h1>
          <p className="text-[#6B6761] mb-6">Your order is on its way.</p>
          <div className="bg-white rounded-lg border border-[#DCD7D0] p-4 mb-6 text-left">
            <p className="text-sm text-[#6B6761]">Order Total</p>
            <p className="text-xl font-bold text-[#2D5A27]">${orderSuccess.total?.toFixed(2)}</p>
          </div>
          <div className="flex gap-3">
            <Link to="/products" className="flex-1">
              <Button className="w-full bg-[#2D5A27] hover:bg-[#1E4219] text-white rounded-full" data-testid="continue-shopping-button">
                Continue Shopping
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (cart.items.length === 0) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-16">
        <div className="max-w-md mx-auto px-4 text-center">
          <ShoppingBag className="w-16 h-16 text-[#DCD7D0] mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-[#1A1A1A] font-['Outfit'] mb-2">Your cart is empty</h1>
          <p className="text-[#6B6761] mb-6">Add some items before checking out</p>
          <Link to="/products">
            <Button className="bg-[#2D5A27] hover:bg-[#1E4219] text-white rounded-full">Browse Products</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6] py-8">
      <div className="max-w-3xl mx-auto px-4">
        {/* Compact header */}
        <h1 className="text-xl font-bold text-[#1A1A1A] font-['Outfit'] mb-6" data-testid="checkout-title">Checkout</h1>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Form — compact */}
          <form onSubmit={handleSubmit} className="lg:col-span-3 space-y-4">
            <div className="bg-white rounded-lg border border-[#DCD7D0] p-5">
              <h2 className="text-sm font-semibold text-[#1A1A1A] mb-4 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-[#2D5A27]" /> Delivery Details
              </h2>
              <div className="space-y-3">
                <div>
                  <Label htmlFor="address" className="text-xs text-[#6B6761]">Address</Label>
                  <Input
                    id="address"
                    value={formData.delivery_address}
                    onChange={(e) => setFormData(p => ({ ...p, delivery_address: e.target.value }))}
                    placeholder="123 Main St, Apt 4"
                    className={errors.delivery_address ? 'border-red-400' : ''}
                    data-testid="delivery-address-input"
                  />
                  {errors.delivery_address && <p className="text-xs text-red-500 mt-1">{errors.delivery_address}</p>}
                </div>
                <div>
                  <Label htmlFor="phone" className="text-xs text-[#6B6761]">Phone</Label>
                  <Input
                    id="phone"
                    value={formData.phone}
                    onChange={(e) => setFormData(p => ({ ...p, phone: e.target.value }))}
                    placeholder="+1 555-123-4567"
                    className={errors.phone ? 'border-red-400' : ''}
                    data-testid="phone-input"
                  />
                  {errors.phone && <p className="text-xs text-red-500 mt-1">{errors.phone}</p>}
                </div>
              </div>
            </div>

            <Button
              type="submit"
              disabled={processing}
              className="w-full bg-[#2D5A27] hover:bg-[#1E4219] text-white h-12 rounded-full text-base font-semibold"
              data-testid="place-order-button"
            >
              {processing ? (
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <><Zap className="w-4 h-4 mr-2" /> Place Order — ${total.toFixed(2)}</>
              )}
            </Button>
          </form>

          {/* Order Summary — compact sidebar */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg border border-[#DCD7D0] p-4 sticky top-4">
              <h3 className="text-sm font-semibold text-[#1A1A1A] mb-3">Order Summary</h3>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {cart.items.map(item => (
                  <div key={item.product_id} className="flex justify-between text-sm">
                    <span className="text-[#6B6761] truncate flex-1">{item.product?.name || 'Item'} x{item.quantity}</span>
                    <span className="text-[#1A1A1A] ml-2 font-medium">${((item.product?.price || 0) * item.quantity).toFixed(2)}</span>
                  </div>
                ))}
              </div>
              <div className="border-t border-[#EBE8E3] mt-3 pt-3 space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-[#6B6761]">Subtotal</span>
                  <span>${cartTotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#6B6761]">Delivery</span>
                  <span className={deliveryFee === 0 ? 'text-[#2D5A27] font-medium' : ''}>{deliveryFee === 0 ? 'FREE' : `$${deliveryFee.toFixed(2)}`}</span>
                </div>
                <div className="flex justify-between font-bold text-base pt-1">
                  <span>Total</span>
                  <span className="text-[#2D5A27]">${total.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

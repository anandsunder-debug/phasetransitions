import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Trash2, Plus, Minus, ShoppingBag, ArrowRight } from 'lucide-react';
import { Button } from '../components/ui/button';
import { useCart } from '../contexts/CartContext';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';

export default function CartPage() {
  const { cart, cartTotal, updateCartItem, removeFromCart, loading } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();

  const handleQuantityChange = async (productId, newQuantity) => {
    if (newQuantity < 1) {
      const result = await removeFromCart(productId);
      if (result.success) {
        toast.success('Item removed from cart');
      }
    } else {
      await updateCartItem(productId, newQuantity);
    }
  };

  const handleRemove = async (productId, productName) => {
    const result = await removeFromCart(productId);
    if (result.success) {
      toast.success(`${productName} removed from cart`);
    }
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-16">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <ShoppingBag className="w-16 h-16 text-[#DCD7D0] mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-[#1A1A1A] font-['Outfit'] mb-2">
            Sign in to view your cart
          </h1>
          <p className="text-[#6B6761] mb-6">
            Please sign in to access your shopping cart
          </p>
          <Link to="/login">
            <Button className="bg-[#2D5A27] hover:bg-[#1E4219] text-white">
              Sign In
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="animate-pulse space-y-4">
            <div className="h-8 w-32 bg-[#EBE8E3] rounded" />
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-white rounded-lg p-4 flex gap-4">
                <div className="w-24 h-24 bg-[#EBE8E3] rounded" />
                <div className="flex-1 space-y-2">
                  <div className="h-5 w-1/3 bg-[#EBE8E3] rounded" />
                  <div className="h-4 w-1/4 bg-[#EBE8E3] rounded" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (cart.items.length === 0) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-16">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <ShoppingBag className="w-16 h-16 text-[#DCD7D0] mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-[#1A1A1A] font-['Outfit'] mb-2">
            Your cart is empty
          </h1>
          <p className="text-[#6B6761] mb-6">
            Looks like you haven't added anything to your cart yet
          </p>
          <Link to="/products">
            <Button className="bg-[#2D5A27] hover:bg-[#1E4219] text-white">
              Start Shopping
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6] py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-bold text-[#1A1A1A] font-['Outfit'] mb-8">
          Shopping Cart
        </h1>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Cart Items */}
          <div className="lg:col-span-2 space-y-4">
            {cart.items.map((item) => (
              <div
                key={item.product_id}
                className="bg-white rounded-lg border border-[#DCD7D0] p-4 flex gap-4"
                data-testid={`cart-item-${item.product_id}`}
              >
                <img
                  src={item.product?.image_url}
                  alt={item.product?.name}
                  className="w-24 h-24 object-cover rounded-md"
                />
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-[#1A1A1A] font-['Outfit'] truncate">
                    {item.product?.name}
                  </h3>
                  <p className="text-sm text-[#6B6761]">
                    ${item.product?.price.toFixed(2)} / {item.product?.unit}
                  </p>
                  
                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center border border-[#DCD7D0] rounded-md">
                      <button
                        onClick={() => handleQuantityChange(item.product_id, item.quantity - 1)}
                        className="p-1 hover:bg-[#EBE8E3] transition-colors"
                        data-testid={`cart-decrease-${item.product_id}`}
                      >
                        <Minus className="w-4 h-4" />
                      </button>
                      <span className="w-8 text-center text-sm font-medium">
                        {item.quantity}
                      </span>
                      <button
                        onClick={() => handleQuantityChange(item.product_id, item.quantity + 1)}
                        className="p-1 hover:bg-[#EBE8E3] transition-colors"
                        data-testid={`cart-increase-${item.product_id}`}
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="flex items-center gap-4">
                      <span className="font-semibold text-[#2D5A27]">
                        ${(item.product?.price * item.quantity).toFixed(2)}
                      </span>
                      <button
                        onClick={() => handleRemove(item.product_id, item.product?.name)}
                        className="text-[#6B6761] hover:text-red-500 transition-colors"
                        data-testid={`cart-remove-${item.product_id}`}
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Order Summary */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg border border-[#DCD7D0] p-6 sticky top-24">
              <h2 className="text-lg font-bold text-[#1A1A1A] font-['Outfit'] mb-4">
                Order Summary
              </h2>

              <div className="space-y-3 text-sm">
                <div className="flex justify-between text-[#6B6761]">
                  <span>Subtotal ({cart.items.length} items)</span>
                  <span>${cartTotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-[#6B6761]">
                  <span>Delivery</span>
                  <span>{cartTotal >= 50 ? 'Free' : '$5.00'}</span>
                </div>
                <div className="border-t border-[#DCD7D0] pt-3 flex justify-between font-semibold text-[#1A1A1A]">
                  <span>Total</span>
                  <span>${(cartTotal + (cartTotal >= 50 ? 0 : 5)).toFixed(2)}</span>
                </div>
              </div>

              {cartTotal < 50 && (
                <p className="text-xs text-[#E47A53] mt-3">
                  Add ${(50 - cartTotal).toFixed(2)} more for free delivery
                </p>
              )}

              <Button
                onClick={() => navigate('/checkout')}
                className="w-full mt-6 bg-[#2D5A27] hover:bg-[#1E4219] text-white rounded-full"
                data-testid="checkout-button"
              >
                Proceed to Checkout
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

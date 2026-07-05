import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, MapPin, Phone, Package, Check, Clock, Truck } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '../contexts/AuthContext';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const statusSteps = ['pending', 'confirmed', 'preparing', 'out_for_delivery', 'delivered'];

const statusConfig = {
  pending: { icon: Clock, label: 'Order Placed', color: 'text-yellow-500' },
  confirmed: { icon: Check, label: 'Confirmed', color: 'text-blue-500' },
  preparing: { icon: Package, label: 'Preparing', color: 'text-purple-500' },
  out_for_delivery: { icon: Truck, label: 'Out for Delivery', color: 'text-orange-500' },
  delivered: { icon: Check, label: 'Delivered', color: 'text-green-500' },
  cancelled: { icon: Clock, label: 'Cancelled', color: 'text-red-500' },
};

export default function OrderDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchOrder = async () => {
      try {
        const { data } = await axios.get(`${API}/orders/${id}`, { withCredentials: true });
        setOrder(data);
      } catch (e) {
        console.error('Failed to fetch order:', e);
        navigate('/orders');
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchOrder();
    }
  }, [id, user, navigate]);

  if (!user) {
    navigate('/login');
    return null;
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="animate-pulse space-y-6">
            <div className="h-8 w-32 bg-[#EBE8E3] rounded" />
            <div className="bg-white rounded-lg p-6 space-y-4">
              <div className="h-6 w-1/3 bg-[#EBE8E3] rounded" />
              <div className="h-4 w-1/2 bg-[#EBE8E3] rounded" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!order) return null;

  const currentStepIndex = statusSteps.indexOf(order.status);
  const StatusIcon = statusConfig[order.status]?.icon || Clock;

  return (
    <div className="min-h-screen bg-[#F9F8F6] py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Back Button */}
        <button
          onClick={() => navigate('/orders')}
          className="flex items-center gap-2 text-[#6B6761] hover:text-[#1A1A1A] mb-8 transition-colors"
          data-testid="back-to-orders"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Orders
        </button>

        {/* Order Header */}
        <div className="bg-white rounded-lg border border-[#DCD7D0] p-6 mb-6">
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-[#1A1A1A] font-['Outfit']">
                Order #{order.id.slice(-8)}
              </h1>
              <p className="text-[#6B6761] mt-1">
                Placed on {new Date(order.created_at).toLocaleString()}
              </p>
            </div>
            <div className={`flex items-center gap-2 ${statusConfig[order.status]?.color}`}>
              <StatusIcon className="w-5 h-5" />
              <span className="font-medium">{statusConfig[order.status]?.label}</span>
            </div>
          </div>

          {/* Progress Steps */}
          {order.status !== 'cancelled' && (
            <div className="flex items-center justify-between mb-6">
              {statusSteps.map((step, idx) => {
                const StepIcon = statusConfig[step].icon;
                const isActive = idx <= currentStepIndex;
                const isCurrent = idx === currentStepIndex;
                
                return (
                  <React.Fragment key={step}>
                    <div className="flex flex-col items-center">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                        isActive ? 'bg-[#2D5A27] text-white' : 'bg-[#EBE8E3] text-[#6B6761]'
                      } ${isCurrent ? 'ring-4 ring-[#2D5A27]/20' : ''}`}>
                        <StepIcon className="w-5 h-5" />
                      </div>
                      <span className={`text-xs mt-2 ${isActive ? 'text-[#2D5A27] font-medium' : 'text-[#6B6761]'}`}>
                        {statusConfig[step].label}
                      </span>
                    </div>
                    {idx < statusSteps.length - 1 && (
                      <div className={`flex-1 h-1 mx-2 rounded ${
                        idx < currentStepIndex ? 'bg-[#2D5A27]' : 'bg-[#EBE8E3]'
                      }`} />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          )}

          {/* Delivery Info */}
          <div className="grid md:grid-cols-2 gap-4 pt-4 border-t border-[#DCD7D0]">
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 text-[#2D5A27] mt-0.5" />
              <div>
                <p className="text-sm text-[#6B6761]">Delivery Address</p>
                <p className="text-[#1A1A1A]">{order.delivery_address}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Phone className="w-5 h-5 text-[#2D5A27] mt-0.5" />
              <div>
                <p className="text-sm text-[#6B6761]">Phone</p>
                <p className="text-[#1A1A1A]">{order.phone}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Order Items */}
        <div className="bg-white rounded-lg border border-[#DCD7D0] p-6">
          <h2 className="text-lg font-bold text-[#1A1A1A] font-['Outfit'] mb-4">
            Order Items
          </h2>

          <div className="space-y-4">
            {order.items.map((item, idx) => (
              <div key={idx} className="flex justify-between items-center py-3 border-b border-[#DCD7D0] last:border-0">
                <div>
                  <p className="font-medium text-[#1A1A1A]">{item.name}</p>
                  <p className="text-sm text-[#6B6761]">
                    {item.quantity} × ${item.price.toFixed(2)} / {item.unit}
                  </p>
                </div>
                <span className="font-medium text-[#1A1A1A]">
                  ${(item.price * item.quantity).toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          <div className="border-t border-[#DCD7D0] mt-4 pt-4 space-y-2">
            <div className="flex justify-between text-sm text-[#6B6761]">
              <span>Subtotal</span>
              <span>${order.total.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm text-[#6B6761]">
              <span>Delivery</span>
              <span>Free</span>
            </div>
            <div className="flex justify-between font-semibold text-lg text-[#1A1A1A] pt-2 border-t border-[#DCD7D0]">
              <span>Total</span>
              <span className="text-[#2D5A27]">${order.total.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

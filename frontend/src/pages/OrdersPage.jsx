import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Package, Clock, ChevronRight, RotateCcw } from 'lucide-react';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { useAuth } from '../contexts/AuthContext';
import { useCart } from '../contexts/CartContext';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const statusColors = {
  pending: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-blue-100 text-blue-800',
  preparing: 'bg-purple-100 text-purple-800',
  out_for_delivery: 'bg-orange-100 text-orange-800',
  delivered: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
};

const statusLabels = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  preparing: 'Preparing',
  out_for_delivery: 'Out for Delivery',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
};

export default function OrdersPage() {
  const { user } = useAuth();
  const { addToCart } = useCart();
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reordering, setReordering] = useState(null);

  useEffect(() => {
    const fetchOrders = async () => {
      try {
        const { data } = await axios.get(`${API}/orders`, { withCredentials: true });
        setOrders(data);
      } catch (e) {
        console.error('Failed to fetch orders:', e);
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchOrders();
    } else {
      setLoading(false);
    }
  }, [user]);

  const handleReorder = async (e, order) => {
    e.stopPropagation();
    setReordering(order.id);
    let added = 0;
    for (const item of order.items) {
      try {
        await addToCart(item.product_id, item.quantity);
        added++;
      } catch (err) {
        console.warn('Reorder skipped item (unavailable):', item.product_id, err);
      }
    }
    setReordering(null);
    if (added > 0) {
      toast.success(`${added} item${added > 1 ? 's' : ''} added to cart`);
      navigate('/checkout');
    } else {
      toast.error('Could not reorder — items may be unavailable');
    }
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-16">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <Package className="w-16 h-16 text-[#DCD7D0] mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-[#1A1A1A] font-['Outfit'] mb-2">Sign in to view orders</h1>
          <p className="text-[#6B6761] mb-6">Please sign in to access your order history</p>
          <Link to="/login">
            <Button className="bg-[#2D5A27] hover:bg-[#1E4219] text-white rounded-full">Sign In</Button>
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
              <div key={`order-skeleton-${i}`} className="bg-white rounded-lg p-6 space-y-3">
                <div className="h-5 w-1/4 bg-[#EBE8E3] rounded" />
                <div className="h-4 w-1/3 bg-[#EBE8E3] rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="min-h-screen bg-[#F9F8F6] py-16">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <Package className="w-16 h-16 text-[#DCD7D0] mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-[#1A1A1A] font-['Outfit'] mb-2">No orders yet</h1>
          <p className="text-[#6B6761] mb-6">Start shopping to see your orders here</p>
          <Link to="/products">
            <Button className="bg-[#2D5A27] hover:bg-[#1E4219] text-white rounded-full">Browse Products</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F8F6] py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-bold text-[#1A1A1A] font-['Outfit'] mb-8">My Orders</h1>

        <div className="space-y-4" data-testid="orders-list">
          {orders.map((order) => (
            <div
              key={order.id}
              className="bg-white rounded-lg border border-[#DCD7D0] p-6 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => navigate(`/orders/${order.id}`)}
              data-testid={`order-${order.id}`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="font-semibold text-[#1A1A1A] font-['Outfit']">
                      Order #{order.id.slice(-8)}
                    </span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[order.status]}`}>
                      {statusLabels[order.status]}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-[#6B6761]">
                    <span className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      {new Date(order.created_at).toLocaleDateString()}
                    </span>
                    <span>{order.items.length} items</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {/* Reorder Button */}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={(e) => handleReorder(e, order)}
                    disabled={reordering === order.id}
                    className="rounded-full border-[#2D5A27] text-[#2D5A27] hover:bg-[#2D5A27] hover:text-white h-8 px-3 text-xs"
                    data-testid={`reorder-${order.id}`}
                  >
                    {reordering === order.id ? (
                      <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin mr-1" />
                    ) : (
                      <RotateCcw className="w-3 h-3 mr-1" />
                    )}
                    Reorder
                  </Button>
                  <span className="font-semibold text-[#2D5A27] text-lg">${order.total.toFixed(2)}</span>
                  <ChevronRight className="w-5 h-5 text-[#6B6761]" />
                </div>
              </div>

              <div className="mt-4 flex items-center gap-2 overflow-x-auto">
                {order.items.slice(0, 4).map((item, idx) => (
                  <div key={`${order.id}-item-${idx}`} className="text-xs text-[#6B6761] bg-[#EBE8E3] px-2 py-1 rounded">
                    {item.name} x {item.quantity}
                  </div>
                ))}
                {order.items.length > 4 && (
                  <span className="text-xs text-[#6B6761]">+{order.items.length - 4} more</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

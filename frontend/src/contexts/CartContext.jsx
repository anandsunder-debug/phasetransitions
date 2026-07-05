import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { useAuth } from './AuthContext';

const CartContext = createContext(null);

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function CartProvider({ children }) {
  const { user } = useAuth();
  const [cart, setCart] = useState({ items: [] });
  const [loading, setLoading] = useState(false);
  const pendingOps = useRef(0);

  const fetchCart = useCallback(async () => {
    if (!user || user === false) {
      setCart({ items: [] });
      return;
    }
    // Skip fetch if optimistic ops are pending
    if (pendingOps.current > 0) return;
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/cart`, { withCredentials: true });
      setCart(data);
    } catch (e) {
      // Error handled silently — cart defaults to empty
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchCart();
  }, [fetchCart]);

  const addToCart = async (productId, quantity = 1) => {
    // Optimistic update — add instantly, sync later
    pendingOps.current++;
    try {
      await axios.post(`${API}/cart/add`, { product_id: productId, quantity }, { withCredentials: true });
      pendingOps.current--;
      await fetchCart();
      return { success: true };
    } catch (e) {
      pendingOps.current--;
      await fetchCart(); // Revert on failure
      return { success: false, error: e.response?.data?.detail || e.message };
    }
  };

  const updateCartItem = async (productId, quantity) => {
    // Optimistic update
    setCart(prev => ({
      ...prev,
      items: prev.items.map(item =>
        item.product_id === productId ? { ...item, quantity } : item
      )
    }));
    pendingOps.current++;
    try {
      await axios.put(`${API}/cart/update`, { product_id: productId, quantity }, { withCredentials: true });
      pendingOps.current--;
      await fetchCart();
      return { success: true };
    } catch (e) {
      pendingOps.current--;
      await fetchCart();
      return { success: false, error: e.response?.data?.detail || e.message };
    }
  };

  const removeFromCart = async (productId) => {
    // Optimistic update — remove instantly
    setCart(prev => ({
      ...prev,
      items: prev.items.filter(item => item.product_id !== productId)
    }));
    pendingOps.current++;
    try {
      await axios.delete(`${API}/cart/remove/${productId}`, { withCredentials: true });
      pendingOps.current--;
      await fetchCart();
      return { success: true };
    } catch (e) {
      pendingOps.current--;
      await fetchCart();
      return { success: false, error: e.response?.data?.detail || e.message };
    }
  };

  const clearCart = async () => {
    setCart({ items: [] });
    try {
      await axios.delete(`${API}/cart/clear`, { withCredentials: true });
      return { success: true };
    } catch (e) {
      await fetchCart();
      return { success: false, error: e.response?.data?.detail || e.message };
    }
  };

  const cartCount = cart.items.reduce((sum, item) => sum + item.quantity, 0);
  const cartTotal = cart.items.reduce((sum, item) => sum + (item.product?.price || 0) * item.quantity, 0);

  return (
    <CartContext.Provider value={{ cart, loading, cartCount, cartTotal, addToCart, updateCartItem, removeFromCart, clearCart, fetchCart }}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
}

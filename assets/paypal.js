window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        mountPayPal: function(validation_data) {
            const container = document.getElementById("paypal-button-container");
            if (!container) return "";

            // Clear container whenever validation status changes
            container.innerHTML = "";

            if (!validation_data || !validation_data.is_valid) {
                return "Payment Locked (Form Incomplete)";
            }

            if (!window.paypal) {
                console.warn("PayPal SDK not loaded.");
                return "PayPal SDK Missing";
            }

            const amount = parseFloat(validation_data.amount) || 0;
            if (amount <= 0) return "Invalid Amount";

            paypal.Buttons({
                style: {
                    layout: 'vertical',
                    color:  'gold',
                    shape:  'rect',
                    label:  'paypal'
                },
                createOrder: function(data, actions) {
                    return fetch('/api/paypal/create-order', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            amount: amount.toFixed(2)
                        })
                    })
                    .then(function(res) {
                        return res.json();
                    })
                    .then(function(orderData) {
                        return orderData.id; // Returns the order ID from your Flask backend to PayPal's SDK
                    });
                },
                onApprove: function(data, actions) {
                    return fetch('/api/paypal/capture-order/' + data.orderID, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    })
                    .then(function(res) {
                        return res.json();
                    })
                    .then(function(details) {
                        console.log('Capture successful:', details);
                        if (details.status === 'COMPLETED') {
                            const storeEl = document.getElementById('paypal-transaction-store');
                            if (storeEl) {
                                storeEl.value = JSON.stringify({
                                    orderID: data.orderID,
                                    payerID: data.payerID,
                                    amount: amount.toFixed(2),
                                    payerName: details.payer && details.payer.name ? details.payer.name.given_name : ""
                                });

                                // Optional: Dispatch an event if Dash needs to detect the store value change
                                storeEl.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    });
                },
                onError: function(err) {
                    console.error('PayPal Checkout Error:', err);
                }
            }).render('#paypal-button-container');

            return "PayPal Mounted ($" + amount.toFixed(2) + ")";
        }
    }
});
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

            // Extract order choices
            const orderData = validation_data.order_data || {};
            if (!orderData.division) {
                return "Form Incomplete (Division Required)";
            }

            const amount = orderData.amount.toFixed(2);

            paypal.Buttons({
                style: {
                    layout: 'vertical',
                    color:  'gold',
                    shape:  'rect',
                    label:  'paypal'
                },
                createOrder: function(data, actions) {
                    return fetch('/pageant/api/paypal/create-order', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            selection_data: orderData
                        })
                    })
                    .then(function(res) {
                        return res.json();
                    })
                    .then(function(orderResponse) {
                        if (orderResponse.error || !orderResponse.id) {
                            console.error("Error creating PayPal order:", orderResponse);
                            throw new Error(orderResponse.message || "Failed to create order");
                        }
                        return orderResponse.id; // Return PayPal order ID to the SDK
                    });
                },
                onApprove: function(data, actions) {
                    const container = document.getElementById("paypal-button-container");
                    if (container) {
                        container.innerHTML = `
                            <div class="alert alert-warning text-center py-3 shadow-sm my-3" role="alert">
                                <div class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></div>
                                <strong>Payment approved! Finalizing your registration...</strong>
                                <div class="small text-muted mt-1">Please do not refresh or close this page.</div>
                            </div>
                        `;
                    }

                    return fetch('/pageant/api/paypal/capture-order/' + data.orderID, {
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
                            // Extract buyer given name across PayPal API v2 schemas
                            let payerGivenName = "";
                            if (details.payment_source && details.payment_source.paypal && details.payment_source.paypal.name) {
                                payerGivenName = details.payment_source.paypal.name.given_name || "";
                            } else if (details.payer && details.payer.name) {
                                payerGivenName = details.payer.name.given_name || "";
                            }

                            // Extract the captured dollar amount directly from PayPal's response
                            const capturedAmount = details.purchase_units?.[0]?.payments?.captures?.[0]?.amount?.value
                                                || details.purchase_units?.[0]?.amount?.value
                                                || "0.00";

                            const payload = {
                                orderID: data.orderID,
                                payerID: data.payerID,
                                amount: capturedAmount,
                                payerName: payerGivenName
                            };

                            // Update dcc.Store via Dash clientside API
                            if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
                                dash_clientside.set_props('paypal-transaction-store', {data: payload});
                            } else {
                                // Fallback for standard DOM input element
                                const storeEl = document.getElementById('paypal-transaction-store');
                                if (storeEl) {
                                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
                                    if (nativeSetter) {
                                        nativeSetter.call(storeEl, JSON.stringify(payload));
                                    } else {
                                        storeEl.value = JSON.stringify(payload);
                                    }
                                    storeEl.dispatchEvent(new Event('input', {bubbles: true}));
                                    storeEl.dispatchEvent(new Event('change', {bubbles: true}));
                                }
                            }
                        }
                    })
                    .catch(function(err) {
                        console.error("Capture Error:", err);
                        if (container) {
                            container.innerHTML = `
                                <div class="alert alert-danger text-center my-3">
                                    There was an error processing your payment. Please refresh and try again or contact support.
                                </div>
                            `;
                        }
                    });
                },
                onError: function(err) {
                    console.error('PayPal Checkout Error:', err);
                }
            }).render('#paypal-button-container');

            return "PayPal Mounted ($" + amount + ")";
        }
    }
});
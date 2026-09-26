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
                    return actions.order.create({
                        purchase_units: [{
                            amount: {
                                value: amount.toFixed(2)
                            }
                        }]
                    });
                },
                onApprove: function(data, actions) {
                    return actions.order.capture().then(function(details) {
                        console.log('Capture successful:', details);
                        if (details.status === 'COMPLETED') {
                            const storeEl = document.getElementById('paypal-transaction-store');
                            storeEl.value = JSON.stringify({
                                    orderID: data.orderID,
                                    payerID: data.payerID,
                                    amount: amount.toFixed(2),
                                    payerName: details.payer ? details.payer.name.given_name : ""
                            });
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
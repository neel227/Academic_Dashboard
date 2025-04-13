window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(data) {
            if (data && data.trigger) {
                var button = document.getElementById('clear_button');
                if (button) {
                    button.click();
                }
            }
            return '';
        }

    }
});
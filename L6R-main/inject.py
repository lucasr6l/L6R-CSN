import sys

with open('index.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Insert Sair button
btn_target = '<button class="btn-header" onclick="abrirRelatorio()"><i class="fa-solid fa-file-pdf"></i> Relatório</button>'
btn_replacement = btn_target + '\n            <button class="btn-header" onclick="doLogout()"><i class="fa-solid fa-arrow-right-from-bracket"></i> Sair</button>'
text = text.replace(btn_target, btn_replacement)

# 2. Insert setInterval auto-refresh inside DOMContentLoaded
# We'll just look for a good place to insert it at the end of the script before </script>
refresh_code = '''
        document.addEventListener("DOMContentLoaded", () => {
            // Auto-refresh a cada 5 minutos (300.000 ms)
            setInterval(() => {
                console.log("Auto-refresh: buscando novos focos...");
                if (typeof atualizarFocosBackendProxy === "function") {
                    atualizarFocosBackendProxy();
                }
            }, 300000);
        });
'''

# 3. Add doLogout function
logout_code = '''
        function doLogout() {
            // Remove token cookie
            document.cookie = 'access_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
            window.location.href = '/login';
        }
'''

if 'function doLogout' not in text:
    if '</script>' in text:
        text = text.replace('</script>', logout_code + '\n' + refresh_code + '\n    </script>', 1)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(text)
print('Modifications applied.')

// Script para mejorar la experiencia de usuario

document.addEventListener('DOMContentLoaded', function() {
    
    // Auto-ocultar alertas después de 5 segundos
    const alerts = document.querySelectorAll('.alert:not(.alert-info)');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
    
    // Scroll suave al hacer clic en "Ver" evento
    document.querySelectorAll('a[href^="#evento-"]').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
                
                // Añadir efecto de destaque
                target.style.transition = 'background-color 0.5s';
                target.style.backgroundColor = '#fff3cd';
                setTimeout(() => {
                    target.style.backgroundColor = '';
                }, 1000);
            }
        });
    });
    
    // Validación de formularios
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });
    
    // Establecer fecha mínima como hoy en los campos de fecha
    const fechaInputs = document.querySelectorAll('input[type="date"]');
    const hoy = new Date().toISOString().split('T')[0];
    fechaInputs.forEach(input => {
        if (!input.value) {
            input.setAttribute('min', hoy);
        }
    });
    
    // Confirmación antes de eliminar
    const deleteLinks = document.querySelectorAll('a[href*="eliminar_evento"]');
    deleteLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            if (!confirm('¿Estás seguro de que deseas eliminar este evento? Esta acción no se puede deshacer.')) {
                e.preventDefault();
            }
        });
    });
    
    // Contador de caracteres para textareas
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        const maxLength = textarea.getAttribute('maxlength');
        if (maxLength) {
            const counter = document.createElement('small');
            counter.className = 'form-text text-muted';
            counter.textContent = `0 / ${maxLength} caracteres`;
            textarea.parentNode.appendChild(counter);
            
            textarea.addEventListener('input', function() {
                const length = this.value.length;
                counter.textContent = `${length} / ${maxLength} caracteres`;
                if (length >= maxLength * 0.9) {
                    counter.classList.add('text-warning');
                } else {
                    counter.classList.remove('text-warning');
                }
            });
        }
    });
    
    // Resaltar evento si viene de URL con hash
    if (window.location.hash) {
        const targetElement = document.querySelector(window.location.hash);
        if (targetElement) {
            setTimeout(() => {
                targetElement.scrollIntoView({ behavior: 'smooth' });
                targetElement.style.backgroundColor = '#fff3cd';
                setTimeout(() => {
                    targetElement.style.backgroundColor = '';
                }, 2000);
            }, 500);
        }
    }
});

// Función para formatear fechas
function formatearFecha(fecha) {
    const meses = [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
    ];
    const date = new Date(fecha);
    return `${date.getDate()} de ${meses[date.getMonth()]} de ${date.getFullYear()}`;
}

// Prevenir envío duplicado de formularios
let formSubmitting = false;
document.addEventListener('submit', function(e) {
    if (formSubmitting) {
        e.preventDefault();
        return false;
    }
    formSubmitting = true;
    
    // Deshabilitar botón de envío
    const submitBtn = e.target.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = true;
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Guardando...';
        
        // Re-habilitar después de 5 segundos por si hay error
        setTimeout(() => {
            formSubmitting = false;
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }, 5000);
    }
});

/**
 *  Web Service
 */
// const axios = require('axios');
// const jQuery = $;

$ = (typeof $ !== 'undefined') ? $ : {};
$.SystemScript = (typeof $.SystemScript !== 'undefined') ? $.SystemScript : {};

$.SystemScript = (function() {
	let __executeGet = function (path) {

        let dfd = $.Deferred();

        axios.get(path)
          .then(function (response) {
            dfd.resolve(response);
          })
          .catch(function (error) {
            dfd.resolve({
                status : 'ERROR',
                message : error
            });

          })
        return dfd.promise();
    };

    let __executePost = function(path, jsonObj) {
        path = path;
        let d = $.Deferred();

        axios.post(path, jsonObj)
        .then(function (response) {
            d.resolve(response)
        })
        .catch(function (error) {
            d.resolve({
                status : 'ERROR',
                message : error
            });
            // console.log('ee')

        });

        return d.promise();
    };


    let __formValidation = function() {

        // Example starter JavaScript for disabling form submissions if there are invalid fields
        (function () {
        'use strict'

        window.addEventListener('load', function () {
            // Fetch all the forms we want to apply custom Bootstrap validation styles to
            var forms = document.getElementsByClassName('needs-validation')

            // Loop over them and prevent submission
            Array.prototype.filter.call(forms, function (form) {
                form.addEventListener('submit', function (event) {
                    if (form.checkValidity() === false) {
                        event.preventDefault()
                        event.stopPropagation()
                    }
                    form.classList.add('was-validated')
                }, false)
            })
        }, false)
        }())
    }

        //action (String)
    let __swalAlertMessage = function (head, mes, action) {
            let d = $.Deferred();
            let response = true;

            swal(head,mes,action)

            d.resolve(response)
            return d.promise();
    }
    let __swalConfirmMessage = function(head, mes, action) {
        let d = $.Deferred();
        swal({
            title: head,
            text: mes,
            type: action,
            confirmButtonText: "Yes",
            showCancelButton: true
        })
        .then((result) => {
            let response = false;

            if (result.value) {
                response = true;
            } else {
                response = false;

            }
            d.resolve(response)
        })
        return d.promise();
    }

    let __dateTimeFormat = function(date_to_format) {
         // Debugging: Log the input date string
         console.log('Original date string:', date_to_format);
            
         // Ensure the input is in the format YYYY-MM-DD HH:MM:SS
         const [datePart, timePart] = date_to_format.split(" ");
         const isoDateString = `${datePart}T${timePart}`; // Convert to ISO format

         // Create a new Date object
         let dateTime = new Date(isoDateString); 

         // Debugging: Log the created date object
         console.log('Created date object:', dateTime);

         // Check if dateTime is valid
         if (isNaN(dateTime.getTime())) {
             return 'Invalid Date';
         }

         // Define month names
         const months = [
             "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"
         ];

         // Get components of the date
         const month = months[dateTime.getMonth()]; // Month name
         const day = dateTime.getDate(); // Day of the month
         const year = dateTime.getFullYear(); // Full year
         let hours = dateTime.getHours(); // Hours
         const minutes = dateTime.getMinutes(); // Minutes

         // Determine AM/PM suffix
         const ampm = hours >= 12 ? 'PM' : 'AM';
         hours = hours % 12; // Convert to 12-hour format
         hours = hours ? hours : 12; // The hour '0' should be '12'

         // Format the final string
         const formattedDate = `${month} ${day}, ${year} at ${hours}:${minutes < 10 ? '0' : ''}${minutes}${ampm}`;
         return formattedDate;
    }

    let __getDefaultOrder = function(element_id_class, column_name, order) {
        // Assuming 'Date Created' is the desired default ordering column
        let orderColumn = column_name; // Change this to whatever field you want to sort by
        let columnIndex = -1;

        // Find the index of the column with the data-order attribute matching 'orderColumn'
        $(`${element_id_class} thead th`).each(function(index) {
            if ($(this).data('order') === orderColumn) {
                columnIndex = index;
            }
        });

        // Return the order array
        return columnIndex !== -1 ? [[columnIndex, order]] : []; // Default to empty if not found
    }

    return {
        executePost : __executePost,
        executeGet : __executeGet,
        formValidation: __formValidation,
        swalAlertMessage: __swalAlertMessage,
        swalConfirmMessage: __swalConfirmMessage,
        dateTimeFormat: __dateTimeFormat,
        getDefaultOrder: __getDefaultOrder,
    };
}());
from django.shortcuts import render


def not_found(request, exception=None):
    return render(request, "office/error.html", {
        "title": "Not found", "message": "That page or record doesn't exist. It may have been deleted.",
    }, status=404)


def server_error(request):
    return render(request, "office/error.html", {
        "title": "Something went wrong",
        "message": "The last action didn't finish. Nothing else was changed. Go back and try again; "
                   "if it keeps happening, note what you clicked and ask for help.",
    }, status=500)
